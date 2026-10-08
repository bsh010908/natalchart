
from __future__ import annotations

from typing import Any


# 비교할 행성
PLANETS = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
)

OUTER_PLANETS = {"uranus", "neptune", "pluto"}


# Aspect별 중심 각도와 허용 Orb
ASPECT_RULES = {
    "conjunction": {"angle": 0.0, "orb": 8.0},
    "sextile": {"angle": 60.0, "orb": 5.0},
    "square": {"angle": 90.0, "orb": 6.0},
    "trine": {"angle": 120.0, "orb": 6.0},
    "opposition": {"angle": 180.0, "orb": 8.0},
}


# 관계 해석에서 상대적으로 강조할 행성
PLANET_WEIGHTS = {
    "sun": 1.25,
    "moon": 1.30,
    "mercury": 1.10,
    "venus": 1.25,
    "mars": 1.15,
    "jupiter": 1.00,
    "saturn": 1.00,
    "uranus": 0.75,
    "neptune": 0.75,
    "pluto": 0.75,
}


# 관계의 특징을 나타내는 테마
RELATIONSHIP_THEMES = {
    "emotional_connection": {
        "moon",
        "venus",
    },
    "communication": {
        "mercury",
    },
    "play_and_energy": {
        "mars",
        "jupiter",
    },
    "affection": {
        "venus",
        "sun",
    },
    "stability_and_routine": {
        "saturn",
    },
    "individuality_and_novelty": {
        "uranus",
    },
}


def angular_distance(
    longitude1: float,
    longitude2: float,
) -> float:
    """
    두 행성의 황경 사이 최단 각도(0~180도).
    """
    difference = abs(
        (longitude1 % 360.0) - (longitude2 % 360.0)
    )

    return min(difference, 360.0 - difference)


def find_aspect(
    angle: float,
) -> dict[str, float | str] | None:
    """
    각도에 해당하는 Aspect를 찾는다.

    여러 Aspect 허용 범위가 겹치면
    허용 Orb 대비 상대 오차가 작은 것을 선택한다.
    """
    candidates = []

    for name, rule in ASPECT_RULES.items():
        orb = abs(angle - rule["angle"])
        allowed_orb = rule["orb"]

        if orb <= allowed_orb:
            candidates.append(
                {
                    "aspect": name,
                    "angle": rule["angle"],
                    "orb": orb,
                    "allowed_orb": allowed_orb,
                    "relative_orb": orb / allowed_orb,
                }
            )

    if not candidates:
        return None

    best = min(
        candidates,
        key=lambda item: (
            item["relative_orb"],
            item["orb"],
        ),
    )

    return {
        "aspect": best["aspect"],
        "angle": best["angle"],
        "orb": best["orb"],
        "allowed_orb": best["allowed_orb"],
    }


def calculate_strength(
    orb: float,
    allowed_orb: float,
) -> float:
    """
    Aspect의 상대적 정확도를 0~1로 변환한다.

    1.0 = 정확한 Aspect
    0.0 = 허용 Orb 경계

    관계의 좋고 나쁨을 의미하지 않는다.
    """
    if allowed_orb <= 0:
        raise ValueError("allowed_orb must be positive")

    return max(
        0.0,
        min(1.0, 1.0 - orb / allowed_orb),
    )


def calculate_importance(
    human_planet: str,
    pet_planet: str,
    strength: float,
) -> float:
    """
    해석 우선순위 계산.

    strength × 두 행성 가중치의 평균

    중요도는 관계의 품질 점수가 아니다.
    """
    human_weight = PLANET_WEIGHTS[human_planet]
    pet_weight = PLANET_WEIGHTS[pet_planet]

    return strength * (
        (human_weight + pet_weight) / 2.0
    )


def is_time_uncertain(
    planet: str,
    chart: dict,
) -> bool:
    """
    출생시간 미상일 때 달 관련 해석에
    불확실성을 표시한다.
    """
    if planet != "moon":
        return False

    if chart.get("birth_time_known") is False:
        return True

    moon_data = chart.get("planets", {}).get("moon", {})

    return bool(moon_data.get("time_uncertain", False))


def get_relationship_themes(
    human_planet: str,
    pet_planet: str,
) -> list[str]:
    """
    행성 조합에 해당하는 관계 테마를 반환한다.

    하나의 Aspect가 여러 테마에 속할 수 있다.
    """
    involved = {human_planet, pet_planet}

    themes = []

    for theme, related_planets in RELATIONSHIP_THEMES.items():
        if involved & related_planets:
            themes.append(theme)

    return themes


def analyze_compatibility(
    human_chart: dict,
    pet_chart: dict,
) -> dict[str, Any]:
    """
    사람과 반려동물의 나탈차트를 비교한다.

    두 차트의 행성 간 Aspect를 계산하고,
    GPT 해석에 필요한 우선순위를 정리한다.

    기존 차트와 분석 결과는 변경하지 않는다.
    """
    human_planets = human_chart["planets"]
    pet_planets = pet_chart["planets"]

    aspects = []

    for human_planet in PLANETS:
        for pet_planet in PLANETS:

            human_data = human_planets[human_planet]
            pet_data = pet_planets[pet_planet]

            # 외행성끼리의 관계는 세대적 특성이 강하므로
            # 개인화된 궁합 해석에서는 제외한다.
            if (
                human_planet in OUTER_PLANETS
                and pet_planet in OUTER_PLANETS
            ):
                continue

            human_longitude = float(
                human_data["longitude"]
            )
            pet_longitude = float(
                pet_data["longitude"]
            )

            angle = angular_distance(
                human_longitude,
                pet_longitude,
            )

            matched = find_aspect(angle)

            if matched is None:
                continue

            orb = float(matched["orb"])
            allowed_orb = float(
                matched["allowed_orb"]
            )

            strength = calculate_strength(
                orb,
                allowed_orb,
            )

            importance = calculate_importance(
                human_planet,
                pet_planet,
                strength,
            )

            time_uncertain = (
                is_time_uncertain(
                    human_planet,
                    human_chart,
                )
                or is_time_uncertain(
                    pet_planet,
                    pet_chart,
                )
            )

            # 불확실한 달 관련 Aspect는
            # 계산 결과를 유지하되 해석 우선순위에서 제외.
            if time_uncertain:
                importance = 0.0

            aspects.append(
                {
                    "human_planet": human_planet,
                    "pet_planet": pet_planet,
                    "aspect": matched["aspect"],
                    "angle": round(angle, 2),
                    "orb": round(orb, 2),
                    "strength": round(strength, 4),
                    "importance": round(
                        importance, 4
                    ),
                    "time_uncertain": time_uncertain,
                    "themes": get_relationship_themes(
                        human_planet,
                        pet_planet,
                    ),
                }
            )

    # 중요도 높은 순서대로 정렬
    aspects.sort(
        key=lambda item: (
            item["time_uncertain"],
            -item["importance"],
            item["orb"],
            item["human_planet"],
            item["pet_planet"],
        )
    )

    # 높은 정확도의 주요 Aspect
    strong_aspects = [
        aspect
        for aspect in aspects
        if (
            not aspect["time_uncertain"]
            and aspect["strength"] >= 0.6
        )
    ]

    # 관계 테마별 중요도 집계
    theme_scores = {
        theme: 0.0
        for theme in RELATIONSHIP_THEMES
    }

    for aspect in aspects:
        if aspect["time_uncertain"]:
            continue

        for theme in aspect["themes"]:
            theme_scores[theme] += aspect["importance"]

    ranked_themes = sorted(
        theme_scores.items(),
        key=lambda item: -item[1],
    )

    dominant_themes = [
        theme
        for theme, score in ranked_themes
        if score > 0
    ][:3]

    return {
        "aspects": aspects,
        "strong_aspects": strong_aspects,
        "dominant_relationship_themes": dominant_themes,
        "theme_scores": {
            theme: round(score, 4)
            for theme, score in theme_scores.items()
        },
        "aspect_count": len(aspects),
    }
