import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from astrology.analysis import OUTER_PLANETS
from pydantic import BaseModel
from typing import TypeVar

from schemas.interpretation import (
    HumanInterpretation,
    PetInterpretation,
    CompatibilityInterpretation,
)
from services.prompts import human as human_prompt, compatibility as compatibility_prompt
from services.prompts.pet import PET_PROMPT


load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# GPT에게 전달할 dominant planet ranking 상위 개수
TOP_PLANETS_FOR_AI = 3


InterpretationType = TypeVar("InterpretationType", bound=BaseModel)


def prepare_chart_for_ai(chart: dict, analysis: dict) -> dict:
    """계산된 차트와 분석을 GPT 입력용으로 정리한다."""
    aspect_analysis = analysis["aspect_analysis"]
    dominant_planet_analysis = analysis["dominant_planet_analysis"]
    strong_aspects = aspect_analysis["strong_aspects"]

    # raw chart 전체를 보내지 않고,
    # 해석에 실제로 필요한 데이터만 정리해서 전달한다.
    #
    # aspect는 analysis에서 이미 계산된 score를 사용한다.
    # Python에서 계산한 analysis가 중요도 판단의 source of truth다.
    #
    # 외행성끼리의 aspect(uranus/neptune/pluto)는 같은 시기에 태어난
    # 개체가 공유하기 쉬운 세대 특성이므로 GPT 입력에서만 제외한다.
    # analysis 원본에는 그대로 남는다.
    ai_chart = {
        "planets": {
            name: {
                "sign": data["sign"],
                "degree": round(data["degree"], 2),
            }
            for name, data in chart["planets"].items()
        },
        "ascendant": chart["ascendant"],
        "mc": chart["mc"],
        "aspects": [
            {
                "planet1": aspect["planet1"],
                "planet2": aspect["planet2"],
                "aspect": aspect["aspect"],
                "orb": round(aspect["orb"], 2),
                "score": round(aspect["score"], 2),
                "strong": aspect in strong_aspects,
            }
            for aspect in aspect_analysis["all_aspects"]
            if not (
                aspect["planet1"] in OUTER_PLANETS
                and aspect["planet2"] in OUTER_PLANETS
            )
        ],
    }

    ai_analysis = {
        "birth_time_known": dominant_planet_analysis["birth_time_known"],

        "elements": {
            name: data["count"]
            for name, data in analysis["elements"].items()
        },

        "dominant_elements": analysis["dominant_elements"],

        "modalities": {
            name: data["count"]
            for name, data in analysis["modalities"].items()
        },

        "dominant_modalities": analysis["dominant_modalities"],

        "dominant_planets": dominant_planet_analysis["dominant_planets"],

        "top_planets": [
            {
                "planet": item["planet"],
                "sign": chart["planets"][item["planet"]]["sign"],
                "score": round(item["score"], 2),
                "components": {
                    name: round(value, 2) if value is not None else None
                    for name, value in item["components"].items()
                },
            }
            for item in dominant_planet_analysis["ranking"][:TOP_PLANETS_FOR_AI]
        ],
    }

    return {"chart": ai_chart, "analysis": ai_analysis}


def parse_interpretation(
    instructions: str,
    data: dict,
    text_format: type[InterpretationType],
) -> InterpretationType:
    """대상별 프롬프트와 응답 스키마로 공통 GPT 호출을 수행한다."""
    response = client.responses.parse(
        model="gpt-6-luna",
        instructions=instructions,
        input=json.dumps(data),
        text_format=text_format,
    )
    if response.output_parsed is None:
        raise RuntimeError("Failed to generate chart interpretation.")
    return response.output_parsed


def interpret_pet(
    pet_name: str,
    pet_type: str,
    pet_breed: str,
    pet_gender: str,
    chart: dict,
    analysis: dict,
) -> PetInterpretation:
    prepared = prepare_chart_for_ai(chart, analysis)
    return parse_interpretation(
        instructions=PET_PROMPT,
        data={
            "pet": {
                "name": pet_name,
                "type": pet_type,
                "breed": pet_breed,
                "gender": pet_gender,
            },
            **prepared,
        },
        text_format=PetInterpretation,
    )


def interpret_human(
    user_name: str,
    chart: dict,
    analysis: dict,
) -> HumanInterpretation:
    instructions = getattr(human_prompt, "HUMAN_INTERPRETATION_PROMPT", None)
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("Define HUMAN_INTERPRETATION_PROMPT in services/prompts/human.py first.")
    return parse_interpretation(
        instructions=instructions,
        data={
            "human": {"name": user_name},
            **prepare_chart_for_ai(chart, analysis),
        },
        text_format=HumanInterpretation,
    )


def interpret_compatibility(
    human: dict,
    pet: dict,
    compatibility_analysis: dict,
) -> CompatibilityInterpretation:
    """사람·반려동물 정보와 이미 계산된 궁합 분석을 전달한다."""
    instructions = getattr(compatibility_prompt, "COMPATIBILITY_INTERPRETATION_PROMPT", None)
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError(
            "Define COMPATIBILITY_INTERPRETATION_PROMPT in services/prompts/compatibility.py first."
        )
    return parse_interpretation(
        instructions=instructions,
        data={
            "human": human,
            "pet": pet,
            "compatibility": compatibility_analysis,
        },
        text_format=CompatibilityInterpretation,
    )
