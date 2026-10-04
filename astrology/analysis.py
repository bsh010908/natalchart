from astrology.calculator import ASPECT_ORB, PLANETS


SIGN_ELEMENTS = {
    "aries": "fire",
    "leo": "fire",
    "sagittarius": "fire",
    "taurus": "earth",
    "virgo": "earth",
    "capricorn": "earth",
    "gemini": "air",
    "libra": "air",
    "aquarius": "air",
    "cancer": "water",
    "scorpio": "water",
    "pisces": "water",
}

SIGN_MODALITIES = {
    "aries": "cardinal",
    "cancer": "cardinal",
    "libra": "cardinal",
    "capricorn": "cardinal",
    "taurus": "fixed",
    "leo": "fixed",
    "scorpio": "fixed",
    "aquarius": "fixed",
    "gemini": "mutable",
    "virgo": "mutable",
    "sagittarius": "mutable",
    "pisces": "mutable",
}

ELEMENTS = ["fire", "earth", "air", "water"]

MODALITIES = ["cardinal", "fixed", "mutable"]

# 키는 calculator.ASPECTS의 aspect 이름과 정확히 일치해야 한다.
ASPECT_WEIGHTS = {
    "conjunction": 1.0,
    "opposition": 1.0,
    "square": 0.9,
    "trine": 0.8,
    "sextile": 0.7,
}

STRONG_ASPECT_THRESHOLD = 0.6

# 전통 rulership. 현대식 공동 ruler(Pluto, Uranus, Neptune)는 사용하지 않는다.
TRADITIONAL_RULERS = {
    "aries": "mars",
    "taurus": "venus",
    "gemini": "mercury",
    "cancer": "moon",
    "leo": "sun",
    "virgo": "mercury",
    "libra": "venus",
    "scorpio": "mars",
    "sagittarius": "jupiter",
    "capricorn": "saturn",
    "aquarius": "saturn",
    "pisces": "jupiter",
}

# 전통 7개 행성의 exaltation sign.
EXALTATIONS = {
    "sun": "aries",
    "moon": "taurus",
    "mercury": "virgo",
    "venus": "pisces",
    "mars": "capricorn",
    "jupiter": "cancer",
    "saturn": "libra",
}

OUTER_PLANETS = {"uranus", "neptune", "pluto"}

# 행성별 aspect score 상위 3개에 순서대로 곱하는 가중치.
ASPECT_INVOLVEMENT_WEIGHTS = [1.0, 0.5, 0.25]

ANGLE_ORB = 10

ANGLE_FACTORS = {
    "asc": 1.0,
    "mc": 1.0,
    "dsc": 0.8,
    "ic": 0.8,
}

# 출생시간이 있을 때 ASC / Sun / Moon sign의 ruler가 받는 점수.
RULERSHIP_WEIGHTS = {
    "ascendant": 0.6,
    "sun": 0.2,
    "moon": 0.2,
}

# 출생시간이 없으면 ASC를 쓸 수 없으므로 Sun / Moon sign의 ruler만 사용한다.
RULERSHIP_WEIGHTS_WITHOUT_TIME = {
    "sun": 0.5,
    "moon": 0.5,
}

DOMICILE_SCORE = 1.0

EXALTATION_SCORE = 0.6

DOMINANT_WEIGHTS = {
    "aspect": 0.35,
    "angularity": 0.30,
    "rulership": 0.25,
    "dignity": 0.10,
}

# 출생시간이 없으면 angularity를 쓸 수 없고 rulership도 Sun/Moon ruler만 남으므로
# rulership 비중을 낮춘다. 정규화 후 실질 비중: aspect 58.33% / rulership 25% / dignity 16.67%
DOMINANT_WEIGHTS_WITHOUT_TIME = {
    "aspect": 0.35,
    "rulership": 0.15,
    "dignity": 0.10,
}

# 1위와의 score 차이가 이 값 미만이면 공동 dominant로 본다.
DOMINANT_SCORE_THRESHOLD = 0.03

MAX_DOMINANT_PLANETS = 2


# 행성별 별자리를 매핑 기준으로 분류해 그룹별 개수와 비율을 계산한다.
def calculate_distribution(
    planets: dict,
    sign_mapping: dict[str, str],
    groups: list[str],
) -> dict:
    if not planets:
        raise ValueError("No planets to analyze")

    counts = {group: 0 for group in groups}
    for name, data in planets.items():
        sign = data["sign"]
        if sign not in sign_mapping:
            raise ValueError(f"Unknown zodiac sign for {name}: {sign!r}")
        counts[sign_mapping[sign]] += 1

    total = len(planets)

    return {
        group: {
            "count": count,
            "ratio": count / total,
        }
        for group, count in counts.items()
    }


# 개수가 가장 많은 그룹을 모두 반환한다. 동점이면 정의된 순서대로 전부 포함한다.
def get_dominant(distribution: dict) -> list[str]:
    max_count = max(data["count"] for data in distribution.values())

    return [
        group
        for group, data in distribution.items()
        if data["count"] == max_count
    ]


# orb를 calculator의 허용 orb 기준 0~1 강도로 변환한다. exact(0°)이면 1, 허용 한계면 0.
def calculate_orb_strength(orb: float) -> float:
    if not 0 <= orb <= ASPECT_ORB:
        raise ValueError(f"Orb out of range 0..{ASPECT_ORB}: {orb!r}")

    return 1 - orb / ASPECT_ORB


# aspect 종류별 가중치와 orb 강도를 곱해 0~1 중요도 점수를 계산한다.
def calculate_aspect_score(aspect: dict) -> float:
    aspect_type = aspect["aspect"]
    if aspect_type not in ASPECT_WEIGHTS:
        raise ValueError(f"Unknown aspect type: {aspect_type}")

    return ASPECT_WEIGHTS[aspect_type] * calculate_orb_strength(aspect["orb"])


# 각 aspect에 점수를 붙여 정렬하고, 강한 aspect와 행성별 aspect 관여도를 계산한다.
def analyze_aspects(aspects: list[dict], planets: dict) -> dict:
    scored_aspects = sorted(
        (
            {**aspect, "score": calculate_aspect_score(aspect)}
            for aspect in aspects
        ),
        key=lambda aspect: (
            -aspect["score"],
            aspect["orb"],
            aspect["planet1"],
            aspect["planet2"],
            aspect["aspect"],
        ),
    )

    planet_aspect_scores = {name: 0.0 for name in planets}
    for aspect in scored_aspects:
        for planet in (aspect["planet1"], aspect["planet2"]):
            if planet not in planet_aspect_scores:
                raise ValueError(f"Unknown planet in aspect: {planet!r}")
            planet_aspect_scores[planet] += aspect["score"]

    return {
        "total": len(scored_aspects),
        "strong_aspects": [
            aspect
            for aspect in scored_aspects
            if aspect["score"] >= STRONG_ASPECT_THRESHOLD
        ],
        "all_aspects": scored_aspects,
        "planet_aspect_scores": planet_aspect_scores,
    }


# 행성의 aspect score 상위 3개를 체감 가중해 0~1 aspect 관여도를 계산한다. 외행성끼리의 aspect는 제외한다.
def calculate_aspect_involvement(planet: str, aspects: list[dict]) -> float:
    scores = sorted(
        (
            aspect["score"]
            for aspect in aspects
            if planet in (aspect["planet1"], aspect["planet2"])
            and not {aspect["planet1"], aspect["planet2"]} <= OUTER_PLANETS
        ),
        reverse=True,
    )

    weighted = sum(
        score * weight
        for score, weight in zip(scores, ASPECT_INVOLVEMENT_WEIGHTS)
    )

    return weighted / sum(ASPECT_INVOLVEMENT_WEIGHTS)


# 두 황경 사이의 최소 각거리(0~180°)를 계산한다.
def calculate_angular_distance(longitude1: float, longitude2: float) -> float:
    distance = abs(longitude1 - longitude2) % 360

    return min(distance, 360 - distance)


# ASC / MC / DSC / IC 중 가장 가까운 angle 기준으로 0~1 angularity를 계산한다.
def calculate_angularity(
    longitude: float,
    ascendant: float,
    mc: float,
) -> float:
    angles = {
        "asc": ascendant,
        "mc": mc,
        "dsc": (ascendant + 180) % 360,
        "ic": (mc + 180) % 360,
    }

    return max(
        ANGLE_FACTORS[name] * max(
            0.0,
            1 - calculate_angular_distance(longitude, angle) / ANGLE_ORB,
        )
        for name, angle in angles.items()
    )


# ASC / Sun / Moon sign의 전통 ruler에게 rulership 점수를 합산한다.
def calculate_rulership_scores(chart: dict) -> dict[str, float]:
    planets = chart["planets"]

    if chart["birth"]["birth_time_known"]:
        sources = [
            (chart["ascendant"]["sign"], RULERSHIP_WEIGHTS["ascendant"]),
            (planets["sun"]["sign"], RULERSHIP_WEIGHTS["sun"]),
            (planets["moon"]["sign"], RULERSHIP_WEIGHTS["moon"]),
        ]
    else:
        sources = [
            (planets["sun"]["sign"], RULERSHIP_WEIGHTS_WITHOUT_TIME["sun"]),
            (planets["moon"]["sign"], RULERSHIP_WEIGHTS_WITHOUT_TIME["moon"]),
        ]

    scores = {name: 0.0 for name in planets}
    for sign, weight in sources:
        scores[TRADITIONAL_RULERS[sign]] += weight

    return scores


# domicile이면 1.0, exaltation이면 0.6, 그 외는 0을 반환한다. detriment와 fall은 감점하지 않는다.
def calculate_dignity(planet: str, sign: str) -> float:
    if TRADITIONAL_RULERS[sign] == planet:
        return DOMICILE_SCORE
    if EXALTATIONS.get(planet) == sign:
        return EXALTATION_SCORE

    return 0.0


# A/G/R/D component를 가중합해 행성별 dominant 점수와 순위를 계산한다.
def analyze_dominant_planets(chart: dict, aspects: list[dict]) -> dict:
    birth_time_known = chart["birth"]["birth_time_known"]

    # 출생시간이 없으면 angularity가 없는 별도 weight를 쓰고, 사용한 weight 합으로 정규화한다.
    weights = DOMINANT_WEIGHTS if birth_time_known else DOMINANT_WEIGHTS_WITHOUT_TIME
    rulership_scores = calculate_rulership_scores(chart)

    ranking = []
    for name, data in chart["planets"].items():
        components = {
            "aspect": calculate_aspect_involvement(name, aspects),
            "angularity": (
                calculate_angularity(
                    data["longitude"],
                    chart["ascendant"]["longitude"],
                    chart["mc"]["longitude"],
                )
                if birth_time_known
                else None
            ),
            "rulership": rulership_scores[name],
            "dignity": calculate_dignity(name, data["sign"]),
        }
        score = sum(
            weight * components[component]
            for component, weight in weights.items()
        ) / sum(weights.values())

        ranking.append({
            "planet": name,
            "score": score,
            "components": components,
        })

    planet_order = list(PLANETS)
    ranking.sort(key=lambda item: (-item["score"], planet_order.index(item["planet"])))

    top_score = ranking[0]["score"]

    return {
        "birth_time_known": birth_time_known,
        "dominant_planets": [
            item["planet"]
            for item in ranking
            if top_score - item["score"] < DOMINANT_SCORE_THRESHOLD
        ][:MAX_DOMINANT_PLANETS],
        "ranking": ranking,
    }


# 차트의 행성 별자리로 원소·모달리티 분포와 우세 그룹을, aspect로 중요도 점수와 dominant planet을 계산한다.
def analyze_chart(chart: dict) -> dict:
    planets = chart["planets"]

    elements = calculate_distribution(planets, SIGN_ELEMENTS, ELEMENTS)
    modalities = calculate_distribution(planets, SIGN_MODALITIES, MODALITIES)
    aspect_analysis = analyze_aspects(chart["aspects"], planets)

    return {
        "elements": elements,
        "dominant_elements": get_dominant(elements),
        "modalities": modalities,
        "dominant_modalities": get_dominant(modalities),
        "aspect_analysis": aspect_analysis,
        "dominant_planet_analysis": analyze_dominant_planets(
            chart,
            aspect_analysis["all_aspects"],
        ),
    }
