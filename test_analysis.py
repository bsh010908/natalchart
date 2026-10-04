import copy
import json
import math

import random

from astrology.analysis import (
    ASPECT_WEIGHTS,
    EXALTATIONS,
    SIGN_ELEMENTS,
    SIGN_MODALITIES,
    STRONG_ASPECT_THRESHOLD,
    TRADITIONAL_RULERS,
    analyze_aspects,
    analyze_chart,
    analyze_dominant_planets,
    calculate_angular_distance,
    calculate_angularity,
    calculate_aspect_involvement,
    calculate_aspect_score,
    calculate_dignity,
    calculate_orb_strength,
    calculate_rulership_scores,
)
from astrology.calculator import ASPECT_ORB, ASPECTS, PLANETS, calculate_aspects


ALL_SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]


# calculate_chart()가 만드는 구조와 같은 형태의 테스트용 차트를 만든다.
def make_chart(signs: dict[str, str]) -> dict:
    return {
        "planets": {
            name: {"longitude": 0.0, "sign": sign, "degree": 0.0}
            for name, sign in signs.items()
        },
        "birth": {"birth_time_known": False},
        "ascendant": None,
        "mc": None,
        "aspects": [],
    }


# 황경으로 calculate_chart()의 planet / ascendant / mc 항목과 같은 형태를 만든다.
def make_point(longitude: float) -> dict:
    return {
        "longitude": longitude,
        "sign": ALL_SIGNS[int(longitude // 30)],
        "degree": longitude % 30,
    }


# 황경으로 차트를 만든다. ascendant가 있으면 출생시간이 있는 차트로 본다.
def make_chart_at(
    longitudes: dict[str, float],
    ascendant: float | None = None,
    mc: float | None = None,
    aspects: list[dict] | None = None,
) -> dict:
    return {
        "birth": {"birth_time_known": ascendant is not None},
        "planets": {name: make_point(lon) for name, lon in longitudes.items()},
        "ascendant": make_point(ascendant) if ascendant is not None else None,
        "mc": make_point(mc) if mc is not None else None,
        "aspects": aspects or [],
    }


# analyze_aspects()를 거친 aspect처럼 score만 가진 항목을 만든다.
def scored(planet1: str, planet2: str, score: float) -> dict:
    return {"planet1": planet1, "planet2": planet2, "score": score}


# fire 2, earth 1, air 4, water 3 / cardinal 5, fixed 2, mutable 3
SAMPLE_CHART = make_chart({
    "sun": "aries",           # fire, cardinal
    "moon": "cancer",         # water, cardinal
    "mercury": "libra",       # air, cardinal
    "venus": "libra",         # air, cardinal
    "mars": "capricorn",      # earth, cardinal
    "jupiter": "leo",         # fire, fixed
    "saturn": "aquarius",     # air, fixed
    "uranus": "gemini",       # air, mutable
    "neptune": "pisces",      # water, mutable
    "pluto": "pisces",        # water, mutable
})


# calculate_aspects()가 만드는 항목과 같은 형태의 aspect를 만든다.
def make_aspect(planet1: str, planet2: str, aspect: str, orb: float) -> dict:
    return {
        "planet1": planet1,
        "planet2": planet2,
        "aspect": aspect,
        "angle": ASPECTS.get(aspect, 0) + orb,
        "orb": orb,
    }


SAMPLE_ASPECTS = [
    make_aspect("mercury", "venus", "conjunction", 3.0),    # 1.0 * 0.5   = 0.5
    make_aspect("moon", "saturn", "opposition", 0.82),      # 1.0 * 0.863 = 0.863
    make_aspect("sun", "mars", "square", 0.0),              # 0.9 * 1.0   = 0.9
    make_aspect("jupiter", "uranus", "sextile", 1.5),       # 0.7 * 0.75  = 0.525
    make_aspect("sun", "jupiter", "trine", 1.2),            # 0.8 * 0.8   = 0.64
]

SAMPLE_CHART["aspects"] = SAMPLE_ASPECTS


def test_mappings_cover_all_signs():
    assert set(SIGN_ELEMENTS) == set(ALL_SIGNS)
    assert set(SIGN_MODALITIES) == set(ALL_SIGNS)


def test_ten_planets_classified():
    analysis = analyze_chart(SAMPLE_CHART)

    assert sum(d["count"] for d in analysis["elements"].values()) == 10
    assert sum(d["count"] for d in analysis["modalities"].values()) == 10
    assert {k: d["count"] for k, d in analysis["elements"].items()} == {
        "fire": 2, "earth": 1, "air": 4, "water": 3,
    }
    assert {k: d["count"] for k, d in analysis["modalities"].items()} == {
        "cardinal": 5, "fixed": 2, "mutable": 3,
    }


def test_ratio_sum_is_one():
    analysis = analyze_chart(SAMPLE_CHART)

    assert math.isclose(sum(d["ratio"] for d in analysis["elements"].values()), 1.0)
    assert math.isclose(sum(d["ratio"] for d in analysis["modalities"].values()), 1.0)
    assert analysis["elements"]["air"]["ratio"] == 0.4


def test_dominant_element():
    assert analyze_chart(SAMPLE_CHART)["dominant_elements"] == ["air"]


def test_dominant_modality():
    assert analyze_chart(SAMPLE_CHART)["dominant_modalities"] == ["cardinal"]


def test_dominant_ties_return_all():
    # fire 3, earth 2, air 3, water 2
    chart = make_chart({
        "sun": "aries",
        "moon": "leo",
        "mercury": "sagittarius",
        "venus": "taurus",
        "mars": "libra",
        "jupiter": "libra",
        "saturn": "aquarius",
        "uranus": "cancer",
        "neptune": "scorpio",
        "pluto": "capricorn",
    })
    analysis = analyze_chart(chart)
    assert analysis["dominant_elements"] == ["fire", "air"]

    # cardinal 4, fixed 4, mutable 2
    chart = make_chart({
        "sun": "aries", "moon": "cancer", "mercury": "libra", "venus": "capricorn",
        "mars": "taurus", "jupiter": "leo", "saturn": "scorpio", "uranus": "aquarius",
        "neptune": "gemini", "pluto": "virgo",
    })
    analysis = analyze_chart(chart)
    assert analysis["dominant_modalities"] == ["cardinal", "fixed"]


def test_invalid_sign_raises():
    for bad_sign in ["Aries", "ophiuchus", "", None]:
        chart = copy.deepcopy(SAMPLE_CHART)
        chart["planets"]["moon"]["sign"] = bad_sign
        try:
            analyze_chart(chart)
        except ValueError as error:
            assert "moon" in str(error)
        else:
            raise AssertionError(f"ValueError not raised for {bad_sign!r}")


def test_input_not_mutated_and_deterministic():
    original = copy.deepcopy(SAMPLE_CHART)
    first = analyze_chart(SAMPLE_CHART)
    second = analyze_chart(SAMPLE_CHART)

    assert SAMPLE_CHART == original
    assert first == second


def test_aspect_weights_match_calculator():
    assert set(ASPECT_WEIGHTS) == set(ASPECTS)


def test_exact_aspect_has_max_strength():
    assert calculate_orb_strength(0) == 1.0
    assert calculate_orb_strength(ASPECT_ORB) == 0.0
    assert calculate_aspect_score(make_aspect("sun", "moon", "conjunction", 0)) == 1.0


def test_score_decreases_as_orb_increases():
    orbs = [0, 0.5, 1, 2, 3, 4, 5, ASPECT_ORB]
    scores = [calculate_aspect_score(make_aspect("sun", "moon", "trine", orb)) for orb in orbs]

    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)


def test_aspect_weight_applied():
    for aspect_type, weight in ASPECT_WEIGHTS.items():
        assert calculate_aspect_score(make_aspect("sun", "moon", aspect_type, 0)) == weight
        assert math.isclose(
            calculate_aspect_score(make_aspect("sun", "moon", aspect_type, ASPECT_ORB / 2)),
            weight * 0.5,
        )


def test_score_in_unit_range():
    for aspect_type in ASPECT_WEIGHTS:
        for step in range(61):
            orb = ASPECT_ORB * step / 60
            score = calculate_aspect_score(make_aspect("sun", "moon", aspect_type, orb))
            assert 0.0 <= score <= 1.0


def test_strong_aspects_threshold_and_order():
    result = analyze_aspects(SAMPLE_ASPECTS, SAMPLE_CHART["planets"])
    strong = result["strong_aspects"]

    assert [(a["planet1"], a["planet2"]) for a in strong] == [
        ("sun", "mars"), ("moon", "saturn"), ("sun", "jupiter"),
    ]
    assert all(a["score"] >= STRONG_ASPECT_THRESHOLD for a in strong)
    assert all(
        a["score"] < STRONG_ASPECT_THRESHOLD
        for a in result["all_aspects"] if a not in strong
    )
    assert [a["score"] for a in strong] == sorted((a["score"] for a in strong), reverse=True)
    assert [a["score"] for a in result["all_aspects"]] == sorted(
        (a["score"] for a in result["all_aspects"]), reverse=True,
    )
    assert result["total"] == 5


def test_tied_scores_sorted_deterministically():
    # 모두 score 0.5. orb → planet1 → planet2 → aspect 순으로 정렬돼야 한다.
    tied = [
        make_aspect("venus", "pluto", "opposition", 3.0),
        make_aspect("mars", "neptune", "conjunction", 3.0),
        make_aspect("mars", "jupiter", "conjunction", 3.0),
    ]
    expected = [("mars", "jupiter"), ("mars", "neptune"), ("venus", "pluto")]

    for order in [tied, list(reversed(tied)), [tied[1], tied[2], tied[0]]]:
        result = analyze_aspects(order, SAMPLE_CHART["planets"])
        assert [(a["planet1"], a["planet2"]) for a in result["all_aspects"]] == expected


def test_planet_aspect_scores_accumulate_both_sides():
    scores = analyze_aspects(SAMPLE_ASPECTS, SAMPLE_CHART["planets"])["planet_aspect_scores"]

    assert list(scores) == list(SAMPLE_CHART["planets"])
    assert math.isclose(scores["sun"], 0.9 + 0.64)          # square + trine
    assert math.isclose(scores["mars"], 0.9)
    assert math.isclose(scores["jupiter"], 0.64 + 0.525)    # trine + sextile
    assert math.isclose(scores["moon"], scores["saturn"])
    assert scores["pluto"] == 0.0


def test_empty_aspects():
    result = analyze_aspects([], SAMPLE_CHART["planets"])

    assert result["total"] == 0
    assert result["strong_aspects"] == []
    assert result["all_aspects"] == []
    assert result["planet_aspect_scores"] == {name: 0.0 for name in SAMPLE_CHART["planets"]}


def test_invalid_aspect_raises():
    cases = [
        (make_aspect("sun", "moon", "quintile", 1.0), "Unknown aspect type: quintile"),
        (make_aspect("sun", "moon", "trine", -0.1), "Orb out of range"),
        (make_aspect("sun", "moon", "trine", ASPECT_ORB + 0.01), "Orb out of range"),
        (make_aspect("sun", "chiron", "trine", 1.0), "Unknown planet"),
    ]
    for aspect, message in cases:
        try:
            analyze_aspects([aspect], SAMPLE_CHART["planets"])
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError(f"ValueError not raised for {aspect}")


def test_extra_aspect_fields_preserved():
    aspect = {**make_aspect("sun", "moon", "trine", 1.0), "time_uncertain": True}
    scored = analyze_aspects([aspect], SAMPLE_CHART["planets"])["all_aspects"][0]

    assert scored["time_uncertain"] is True
    assert scored["angle"] == aspect["angle"]
    assert "score" not in aspect


# ASC Virgo 10.68°, MC Gemini 9.4°, Sun Taurus, Moon Sagittarius
TIMED_LONGITUDES = {
    "sun": 56.87,        # taurus
    "moon": 259.6,       # sagittarius
    "mercury": 62.89,    # gemini, MC에서 6.51°
    "venus": 17.4,       # aries (detriment)
    "mars": 354.64,      # pisces
    "jupiter": 1.3,      # aries
    "saturn": 324.98,    # aquarius (domicile)
    "uranus": 45.51,     # taurus
    "neptune": 354.98,   # pisces
    "pluto": 298.52,     # capricorn
}
TIMED_CHART = make_chart_at(
    TIMED_LONGITUDES,
    ascendant=160.68,
    mc=69.4,
    aspects=[
        make_aspect("mars", "neptune", "conjunction", 0.34),
        make_aspect("sun", "saturn", "square", 1.885),
        make_aspect("mercury", "jupiter", "sextile", 1.599),
        make_aspect("neptune", "pluto", "sextile", 3.54),
    ],
)


def get_ranking_item(result: dict, planet: str) -> dict:
    return next(item for item in result["ranking"] if item["planet"] == planet)


def test_aspect_involvement_formula():
    aspects = [scored("sun", "moon", 0.9), scored("sun", "mars", 0.6), scored("sun", "venus", 0.4)]

    assert calculate_aspect_involvement("sun", aspects) == (0.9 * 1.0 + 0.6 * 0.5 + 0.4 * 0.25) / 1.75
    assert calculate_aspect_involvement("sun", aspects[:1]) == 0.9 / 1.75
    assert calculate_aspect_involvement("sun", aspects[:2]) == (0.9 + 0.6 * 0.5) / 1.75
    assert calculate_aspect_involvement("moon", aspects) == 0.9 / 1.75
    assert calculate_aspect_involvement("pluto", aspects) == 0.0


def test_aspect_involvement_uses_top_three_only():
    aspects = [
        scored("sun", "venus", 0.4),
        scored("sun", "jupiter", 0.3),
        scored("sun", "moon", 0.9),
        scored("sun", "mars", 0.6),
    ]
    expected = (0.9 * 1.0 + 0.6 * 0.5 + 0.4 * 0.25) / 1.75

    assert calculate_aspect_involvement("sun", aspects) == expected
    assert calculate_aspect_involvement("sun", list(reversed(aspects))) == expected
    assert calculate_aspect_involvement("sun", aspects + [scored("sun", "saturn", 0.05)]) == expected


def test_outer_planet_pairs_excluded():
    aspects = [
        scored("uranus", "neptune", 0.9),
        scored("uranus", "pluto", 0.8),
        scored("neptune", "pluto", 0.7),
    ]

    for planet in ["uranus", "neptune", "pluto"]:
        assert calculate_aspect_involvement(planet, aspects) == 0.0


def test_outer_planet_with_inner_planet_included():
    aspects = [
        scored("mars", "neptune", 0.9),
        scored("sun", "pluto", 0.8),
        scored("saturn", "uranus", 0.7),
        scored("neptune", "pluto", 1.0),
    ]

    assert calculate_aspect_involvement("mars", aspects) == 0.9 / 1.75
    assert calculate_aspect_involvement("neptune", aspects) == 0.9 / 1.75
    assert calculate_aspect_involvement("pluto", aspects) == 0.8 / 1.75
    assert calculate_aspect_involvement("uranus", aspects) == 0.7 / 1.75


def test_traditional_rulership_mapping():
    assert TRADITIONAL_RULERS == {
        "aries": "mars", "taurus": "venus", "gemini": "mercury", "cancer": "moon",
        "leo": "sun", "virgo": "mercury", "libra": "venus", "scorpio": "mars",
        "sagittarius": "jupiter", "capricorn": "saturn", "aquarius": "saturn",
        "pisces": "jupiter",
    }
    assert set(TRADITIONAL_RULERS) == set(ALL_SIGNS)


def test_chart_ruler_and_dispositors_with_birth_time():
    scores = calculate_rulership_scores(TIMED_CHART)

    assert scores["mercury"] == 0.6     # ASC virgo
    assert scores["venus"] == 0.2       # Sun taurus
    assert scores["jupiter"] == 0.2     # Moon sagittarius
    assert sum(1 for score in scores.values() if score > 0) == 3


def test_rulership_sums_when_same_planet_matches():
    # ASC scorpio, Sun aries, Moon scorpio → mars가 세 조건 모두 해당
    chart = make_chart_at({**TIMED_LONGITUDES, "sun": 10.0, "moon": 220.0}, ascendant=215.0, mc=125.0)
    assert math.isclose(calculate_rulership_scores(chart)["mars"], 1.0)

    # Sun과 Moon만 같은 ruler
    chart = make_chart_at({**TIMED_LONGITUDES, "sun": 125.0, "moon": 130.0}, ascendant=160.68, mc=69.4)
    scores = calculate_rulership_scores(chart)
    assert math.isclose(scores["sun"], 0.4)
    assert scores["mercury"] == 0.6


def test_dispositors_without_birth_time():
    scores = calculate_rulership_scores(make_chart_at(TIMED_LONGITUDES))
    assert scores["venus"] == 0.5
    assert scores["jupiter"] == 0.5
    assert scores["mercury"] == 0.0

    scores = calculate_rulership_scores(make_chart_at({**TIMED_LONGITUDES, "sun": 125.0, "moon": 130.0}))
    assert scores["sun"] == 1.0


def test_angularity_each_angle():
    # ASC 100, MC 10 → DSC 280, IC 190
    assert calculate_angularity(100, 100, 10) == 1.0
    assert calculate_angularity(10, 100, 10) == 1.0
    assert calculate_angularity(280, 100, 10) == 0.8
    assert calculate_angularity(190, 100, 10) == 0.8
    assert math.isclose(calculate_angularity(105, 100, 10), 0.5)
    assert math.isclose(calculate_angularity(95, 100, 10), 0.5)
    assert math.isclose(calculate_angularity(285, 100, 10), 0.4)


def test_angularity_uses_max_not_sum():
    # ASC 100, MC 95 → 97은 ASC에서 3° (0.7), MC에서 2° (0.8)
    assert math.isclose(calculate_angularity(97, 100, 95), 0.8)


def test_angular_distance_wraps_360():
    assert calculate_angular_distance(359, 1) == 2
    assert calculate_angular_distance(1, 359) == 2
    assert calculate_angular_distance(0, 180) == 180
    assert calculate_angular_distance(350, 10) == 20
    assert math.isclose(calculate_angularity(1, 359, 90), 0.8)
    assert math.isclose(calculate_angularity(357, 2, 90), 0.5)


def test_angularity_zero_beyond_orb():
    assert calculate_angularity(110, 100, 10) == 0.0
    assert calculate_angularity(130, 100, 10) == 0.0
    assert calculate_angularity(55, 100, 10) == 0.0


def test_dignity_domicile():
    for sign, planet in TRADITIONAL_RULERS.items():
        assert calculate_dignity(planet, sign) == 1.0


def test_dignity_exaltation():
    assert EXALTATIONS == {
        "sun": "aries", "moon": "taurus", "mercury": "virgo", "venus": "pisces",
        "mars": "capricorn", "jupiter": "cancer", "saturn": "libra",
    }
    assert calculate_dignity("sun", "aries") == 0.6
    assert calculate_dignity("saturn", "libra") == 0.6
    assert calculate_dignity("venus", "pisces") == 0.6
    # mercury는 virgo가 domicile이자 exaltation → domicile 1.0
    assert calculate_dignity("mercury", "virgo") == 1.0


def test_detriment_and_fall_not_penalized():
    detriment = [("sun", "aquarius"), ("moon", "capricorn"), ("venus", "aries"), ("mars", "libra"), ("saturn", "cancer")]
    fall = [("sun", "libra"), ("moon", "scorpio"), ("mars", "cancer"), ("jupiter", "capricorn"), ("saturn", "aries")]

    for planet, sign in detriment + fall:
        assert calculate_dignity(planet, sign) == 0.0


def test_outer_planet_dignity_is_zero():
    for planet in ["uranus", "neptune", "pluto"]:
        for sign in ALL_SIGNS:
            assert calculate_dignity(planet, sign) == 0.0


def test_dominant_without_birth_time_excludes_angularity():
    chart = make_chart_at(TIMED_LONGITUDES, aspects=TIMED_CHART["aspects"])
    result = analyze_chart(chart)["dominant_planet_analysis"]

    assert result["birth_time_known"] is False
    assert all(item["components"]["angularity"] is None for item in result["ranking"])


def test_dominant_without_birth_time_renormalized():
    chart = make_chart_at(TIMED_LONGITUDES, aspects=TIMED_CHART["aspects"])
    result = analyze_chart(chart)["dominant_planet_analysis"]

    for item in result["ranking"]:
        c = item["components"]
        expected = (0.35 * c["aspect"] + 0.25 * c["rulership"] + 0.10 * c["dignity"]) / 0.70
        assert math.isclose(item["score"], expected)

    # Sun과 Moon이 모두 Leo, aspect 없음 → sun: R 1.0, D 1.0 → (0.25 + 0.10) / 0.70 = 0.5
    chart = make_chart_at({**TIMED_LONGITUDES, "sun": 125.0, "moon": 130.0})
    sun = get_ranking_item(analyze_dominant_planets(chart, []), "sun")
    assert math.isclose(sun["score"], 0.5)


def test_dominant_with_birth_time_formula():
    result = analyze_chart(TIMED_CHART)["dominant_planet_analysis"]

    assert result["birth_time_known"] is True
    for item in result["ranking"]:
        c = item["components"]
        expected = 0.35 * c["aspect"] + 0.30 * c["angularity"] + 0.25 * c["rulership"] + 0.10 * c["dignity"]
        assert math.isclose(item["score"], expected)

    mercury = get_ranking_item(result, "mercury")
    assert result["dominant_planets"] == ["mercury"]
    assert math.isclose(mercury["components"]["angularity"], 1 - 6.51 / 10)
    assert mercury["components"]["rulership"] == 0.6
    assert mercury["components"]["dignity"] == 1.0
    assert get_ranking_item(result, "neptune")["components"]["aspect"] == get_ranking_item(result, "mars")["components"]["aspect"]


def test_ranking_order_deterministic():
    result = analyze_dominant_planets(TIMED_CHART, analyze_chart(TIMED_CHART)["aspect_analysis"]["all_aspects"])
    scores = [item["score"] for item in result["ranking"]]
    assert scores == sorted(scores, reverse=True)

    # 모두 0점이면 PLANETS 순서
    chart = make_chart_at({name: 300.0 for name in PLANETS})
    chart["planets"]["sun"]["sign"] = "capricorn"
    zero = analyze_dominant_planets(chart, [])
    assert [item["planet"] for item in zero["ranking"] if item["score"] == 0.0] == [
        name for name in PLANETS if name != "saturn"
    ]

    # chart["planets"] 입력 순서가 달라도 같은 ranking
    shuffled = copy.deepcopy(TIMED_CHART)
    shuffled["planets"] = dict(reversed(list(shuffled["planets"].items())))
    assert analyze_chart(shuffled)["dominant_planet_analysis"] == analyze_chart(TIMED_CHART)["dominant_planet_analysis"]


# Sun taurus → venus, Moon sagittarius → jupiter, 행성 모두 dignity 없음, aspect는 Mars-Neptune 하나
TIE_LONGITUDES = {
    "sun": 40.0, "moon": 250.0, "mercury": 10.0, "venus": 15.0, "mars": 340.0,
    "jupiter": 20.0, "saturn": 345.0, "uranus": 50.0, "neptune": 341.0, "pluto": 290.0,
}


def test_exact_tie_gives_multiple_dominants():
    chart = make_chart_at(TIE_LONGITUDES)
    result = analyze_dominant_planets(chart, [scored("mars", "neptune", 1.0)])

    assert result["dominant_planets"] == ["mars", "neptune"]
    assert [item["planet"] for item in result["ranking"][:2]] == ["mars", "neptune"]


def test_near_tie_is_not_co_dominant():
    chart = make_chart_at(TIE_LONGITUDES)
    result = analyze_dominant_planets(chart, [scored("mars", "neptune", 1.0), scored("mars", "saturn", 0.001)])

    assert result["dominant_planets"] == ["mars"]
    assert result["ranking"][1]["planet"] == "neptune"


def test_dominant_input_not_mutated_and_deterministic():
    for chart in [TIMED_CHART, make_chart_at(TIMED_LONGITUDES, aspects=TIMED_CHART["aspects"])]:
        original = copy.deepcopy(chart)
        first = analyze_chart(chart)
        second = analyze_chart(chart)

        assert chart == original
        assert first == second


def test_components_and_scores_in_unit_range():
    rng = random.Random(20261004)

    for i in range(300):
        longitudes = {name: rng.uniform(0, 360) for name in PLANETS}
        timed = i % 2 == 0
        chart = make_chart_at(
            longitudes,
            ascendant=rng.uniform(0, 360) if timed else None,
            mc=rng.uniform(0, 360) if timed else None,
            aspects=calculate_aspects(longitudes),
        )
        result = analyze_chart(chart)["dominant_planet_analysis"]

        assert result["dominant_planets"]
        for item in result["ranking"]:
            assert 0.0 <= item["score"] <= 1.0
            for name, value in item["components"].items():
                if name == "angularity" and not timed:
                    assert value is None
                else:
                    assert 0.0 <= value <= 1.0


def test_existing_analysis_keys_unchanged():
    analysis = analyze_chart(TIMED_CHART)

    assert list(analysis) == [
        "elements", "dominant_elements", "modalities", "dominant_modalities",
        "aspect_analysis", "dominant_planet_analysis",
    ]
    assert "planet_aspect_scores" in analysis["aspect_analysis"]
    assert analysis["aspect_analysis"] == analyze_aspects(TIMED_CHART["aspects"], TIMED_CHART["planets"])


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")

    print(json.dumps(analyze_chart(SAMPLE_CHART), indent=2))
