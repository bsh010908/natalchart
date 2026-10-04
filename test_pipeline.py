import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

# 실제 OpenAI 키 대신 테스트용 값을 쓴다. client는 아래에서 가짜로 교체한다.
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

from astrology.analysis import analyze_chart
from astrology.interpreter import interpret_chart
from db.database import get_db
from db.models import Pet, User
from main import app
from schemas.interpretation import Interpretation


SAMPLE_INTERPRETATION = Interpretation.model_validate({
    "title": "집사 마음 탐지기",
    "summary": "요약",
    "keywords": ["호기심", "간식"],
    "big_three": {
        "sun": {"sign": "taurus", "title": "t", "description": "d"},
        "moon": {"sign": "sagittarius", "title": "t", "description": "d"},
        "ascendant": {"sign": "virgo", "title": "t", "description": "d"},
    },
    "profile": {
        "personality": "p",
        "emotional_world": "e",
        "communication": "c",
        "social_style": "s",
        "play_and_curiosity": "pc",
    },
    "owner_tips": ["tip"],
})

REQUEST = {
    "user_name": "tester",
    "user_email": "tester@example.com",
    "pet_name": "콩이",
    "pet_type": "dog",
    "pet_gender": "female",
    "pet_breed": "maltese",
    "pet_birth_date": "2022-05-17",
    "pet_birth_time": "14:20:00",
    "city": "Austin, TX, USA",
}


# 네트워크 지오코딩 없이 calculate_chart()가 동작하도록 Austin 좌표를 고정한다.
def fake_birth_data(birth_date, birth_time, birth_place):
    effective_time = birth_time if birth_time is not None else datetime.min.time().replace(hour=12)
    local_datetime = datetime.combine(birth_date, effective_time, tzinfo=ZoneInfo("America/Chicago"))

    return {
        "latitude": 30.2711286,
        "longitude": -97.7436995,
        "timezone": "America/Chicago",
        "birth_time_known": birth_time is not None,
        "local_datetime": local_datetime,
        "utc_datetime": local_datetime.astimezone(timezone.utc),
    }


# client.responses.parse() 호출 인자를 기록하는 가짜 OpenAI client.
class FakeOpenAI:
    def __init__(self):
        self.calls = []
        self.responses = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=SAMPLE_INTERPRETATION)


# MySQL 대신 add / flush / commit만 흉내 내는 세션.
class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if isinstance(obj, Pet):
                obj.pet_id = 4

    def commit(self):
        for obj in self.added:
            if isinstance(obj, User):
                obj.user_id = 7
        self.committed = True


# 실제 calculate_chart → analyze_chart → interpret_chart → API 흐름을 실행하고 호출 기록을 반환한다.
def run_request(request: dict) -> dict:
    session = FakeSession()
    fake_openai = FakeOpenAI()
    analyses = []
    interpret_calls = []

    def spy_analyze(chart):
        result = analyze_chart(chart)
        analyses.append(result)
        return result

    def spy_interpret(**kwargs):
        interpret_calls.append(kwargs)
        return interpret_chart(**kwargs)

    app.dependency_overrides[get_db] = lambda: session
    try:
        with (
            patch("astrology.calculator.get_birth_data", fake_birth_data),
            patch("astrology.interpreter.client", fake_openai),
            patch("api.charts.analyze_chart", spy_analyze),
            patch("api.charts.interpret_chart", spy_interpret),
        ):
            response = TestClient(app).post("/api/charts", json=request)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text

    return {
        "body": response.json(),
        "session": session,
        "analyses": analyses,
        "interpret_calls": interpret_calls,
        "openai_calls": fake_openai.calls,
    }


def test_analyze_chart_called_once_per_request():
    result = run_request(REQUEST)

    assert len(result["analyses"]) == 1
    assert len(result["interpret_calls"]) == 1
    assert len(result["openai_calls"]) == 1


def test_same_analysis_object_passed_to_interpretation():
    result = run_request(REQUEST)

    assert result["interpret_calls"][0]["analysis"] is result["analyses"][0]


def test_analysis_reaches_gpt_input():
    result = run_request(REQUEST)
    analysis = result["analyses"][0]
    call = result["openai_calls"][0]
    gpt_input = json.loads(call["input"])

    assert list(gpt_input) == ["pet", "chart", "analysis"]
    assert "HOW TO USE THE INPUT" in call["instructions"]
    assert call["text_format"] is Interpretation

    ai_analysis = gpt_input["analysis"]
    assert ai_analysis["birth_time_known"] is True
    assert ai_analysis["dominant_elements"] == analysis["dominant_elements"]
    assert ai_analysis["dominant_modalities"] == analysis["dominant_modalities"]
    assert ai_analysis["elements"] == {k: v["count"] for k, v in analysis["elements"].items()}
    assert ai_analysis["modalities"] == {k: v["count"] for k, v in analysis["modalities"].items()}

    dominant = analysis["dominant_planet_analysis"]
    assert ai_analysis["dominant_planets"] == dominant["dominant_planets"]
    assert [p["planet"] for p in ai_analysis["top_planets"]] == [
        item["planet"] for item in dominant["ranking"][:3]
    ]
    assert set(ai_analysis["top_planets"][0]["components"]) == {"aspect", "angularity", "rulership", "dignity"}

    # aspects는 analysis 순서(score 내림차순)이고 strong 표시가 strong_aspects와 일치한다.
    aspect_analysis = analysis["aspect_analysis"]
    ai_aspects = gpt_input["chart"]["aspects"]
    assert [(a["planet1"], a["planet2"], a["aspect"]) for a in ai_aspects] == [
        (a["planet1"], a["planet2"], a["aspect"]) for a in aspect_analysis["all_aspects"]
    ]
    assert sum(a["strong"] for a in ai_aspects) == len(aspect_analysis["strong_aspects"])
    assert "houses" not in gpt_input["chart"]


def test_response_includes_analysis_and_chart():
    result = run_request(REQUEST)
    body = result["body"]
    analysis = result["analyses"][0]

    assert list(body) == ["user_id", "pet_id", "interpretation", "analysis", "chart"]
    assert body["analysis"] == json.loads(json.dumps(analysis))
    assert list(body["analysis"]) == [
        "elements", "dominant_elements", "modalities", "dominant_modalities",
        "aspect_analysis", "dominant_planet_analysis",
    ]
    assert list(body["chart"]) == ["birth", "planets", "houses", "ascendant", "mc", "aspects"]
    assert len(body["chart"]["houses"]) == 12
    assert all("score" not in aspect for aspect in body["chart"]["aspects"])


def test_interpretation_schema_preserved():
    body = run_request(REQUEST)["body"]

    assert Interpretation.model_validate(body["interpretation"]) == SAMPLE_INTERPRETATION
    assert list(body["interpretation"]) == ["title", "summary", "keywords", "big_three", "profile", "owner_tips"]


def test_db_ids_preserved():
    result = run_request(REQUEST)

    pet, user = result["session"].added

    assert result["body"]["user_id"] == 7
    assert result["body"]["pet_id"] == 4
    assert result["session"].committed
    assert (type(pet), type(user)) == (Pet, User)
    assert user.pet_id == pet.pet_id


def test_without_birth_time():
    result = run_request({**REQUEST, "pet_birth_time": None})
    body = result["body"]
    ai_analysis = json.loads(result["openai_calls"][0]["input"])["analysis"]

    assert body["chart"]["ascendant"] is None
    assert body["analysis"]["dominant_planet_analysis"]["birth_time_known"] is False
    assert ai_analysis["birth_time_known"] is False
    assert all(p["components"]["angularity"] is None for p in ai_analysis["top_planets"])


def test_openapi_docs_available():
    client = TestClient(app)

    assert client.get("/docs").status_code == 200
    assert "/api/charts" in client.get("/openapi.json").json()["paths"]


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")

    result = run_request(REQUEST)
    print(json.dumps(json.loads(result["openai_calls"][0]["input"]), ensure_ascii=False, indent=2))
