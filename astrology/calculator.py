import logging
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import swisseph as swe
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder


logger = logging.getLogger(__name__)


@contextmanager
def calculation_step(step: str):
    """Log fixed internal labels and exception types, never exception text or inputs."""
    try:
        yield
    except Exception as exc:
        logger.error(
            "Chart calculation failed: internal_step=%s exception_type=%s",
            step, type(exc).__name__,
        )
        raise


PLANETS = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}


ZODIAC_SIGNS = [
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
]

ASPECTS = {
    "conjunction": 0,
    "sextile": 60,
    "square": 90,
    "trine": 120,
    "opposition": 180,
}

ASPECT_ORB = 6

# 출생 장소를 찾아 좌표와 현지·UTC 출생 시각을 반환한다.
def get_birth_data(
    birth_date: date,
    birth_time: time | None,
    birth_place: str,
) -> dict:
    with calculation_step("geocoder_initialization"):
        geolocator = Nominatim(user_agent="pet_natal_chart", timeout=10)

    with calculation_step("geocoding"):
        location = geolocator.geocode(birth_place)
        if location is None:
            raise ValueError(f"Birth place not found: {birth_place}")

        latitude = location.latitude
        longitude = location.longitude

    with calculation_step("timezone_finder_initialization"):
        timezone_finder = TimezoneFinder()

    with calculation_step("timezone_lookup"):
        timezone_name = timezone_finder.timezone_at(
            lat=latitude,
            lng=longitude,
        )
        if timezone_name is None:
            raise ValueError(f"Timezone not found: {birth_place}")

    with calculation_step("birth_datetime_conversion"):
        effective_birth_time = birth_time if birth_time is not None else time(12)
        local_datetime = datetime.combine(
            birth_date,
            effective_birth_time,
            tzinfo=ZoneInfo(timezone_name),
        )
        utc_datetime = local_datetime.astimezone(timezone.utc)

    return {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name,
        "birth_time_known": birth_time is not None,
        "local_datetime": local_datetime,
        "utc_datetime": utc_datetime,
    }


# 생년월일시를 UTC 기준 율리우스일로 변환한다.
def to_julian_day(birth_datetime: datetime) -> float:
    utc_datetime = birth_datetime.astimezone(timezone.utc)

    hour = (
        utc_datetime.hour
        + utc_datetime.minute / 60
        + utc_datetime.second / 3600
    )

    return swe.julday(
        utc_datetime.year,
        utc_datetime.month,
        utc_datetime.day,
        hour,
    )


# 율리우스일을 기준으로 각 행성의 황경을 계산한다.
def calculate_planets(julian_day: float) -> dict[str, float]:
    return {
        name: swe.calc_ut(julian_day, planet)[0][0]
        for name, planet in PLANETS.items()
    }


# 황경을 별자리 이름과 해당 별자리 내 각도로 변환한다.
def get_zodiac_sign(longitude: float) -> tuple[str, float]:
    sign_index = int(longitude // 30)
    degree = longitude % 30

    return ZODIAC_SIGNS[sign_index], degree


# 출생 정보로 출생 시각, 행성, 하우스, 애스펙트 차트를 계산한다.
def calculate_chart(
    birth_date: date,
    birth_time: time | None,
    birth_place: str,
) -> dict:
    birth_data = get_birth_data(birth_date, birth_time, birth_place)
    with calculation_step("julian_day"):
        julian_day = to_julian_day(birth_data["utc_datetime"])

    with calculation_step("planet_calculation"):
        planet_longitudes = calculate_planets(julian_day)

    with calculation_step("zodiac_conversion"):
        planets = {
            name: {
                "longitude": longitude,
                "sign": sign,
                "degree": degree,
            }
            for name, longitude in planet_longitudes.items()
            for sign, degree in [get_zodiac_sign(longitude)]
        }

    houses = None
    if birth_time is not None:
        with calculation_step("house_calculation"):
            houses = calculate_houses(
                julian_day,
                birth_data["latitude"],
                birth_data["longitude"],
            )

    with calculation_step("aspect_calculation"):
        aspects = calculate_aspects(planet_longitudes)

    if birth_time is None:
        planets["moon"]["time_uncertain"] = True
        for aspect in aspects:
            if "moon" in (aspect["planet1"], aspect["planet2"]):
                aspect["time_uncertain"] = True

    return {
        "birth": birth_data,
        "planets": planets,
        "houses": houses["houses"] if houses is not None else None,
        "ascendant": houses["ascendant"] if houses is not None else None,
        "mc": houses["mc"] if houses is not None else None,
        "aspects": aspects,
    }


# 출생 시각과 위치를 바탕으로 하우스, 상승점, 중천점을 계산한다.
def calculate_houses(
    julian_day: float,
    latitude: float,
    longitude: float,
) -> dict:
    cusps, ascmc = swe.houses(
        julian_day,
        latitude,
        longitude,
        b"P",
    )

    houses = {
        house_number: {
            "longitude": cusp,
            "sign": sign,
            "degree": degree,
        }
        for house_number, cusp in enumerate(cusps, start=1)
        for sign, degree in [get_zodiac_sign(cusp)]
    }

    asc_longitude = ascmc[0]
    mc_longitude = ascmc[1]

    asc_sign, asc_degree = get_zodiac_sign(asc_longitude)
    mc_sign, mc_degree = get_zodiac_sign(mc_longitude)

    return {
        "houses": houses,
        "ascendant": {
            "longitude": asc_longitude,
            "sign": asc_sign,
            "degree": asc_degree,
        },
        "mc": {
            "longitude": mc_longitude,
            "sign": mc_sign,
            "degree": mc_degree,
        },
    }


# 행성 간 각도와 허용 오차를 비교해 애스펙트를 찾는다.
def calculate_aspects(planets: dict[str, float]) -> list[dict]:
    planet_items = list(planets.items())
    aspects = []

    for i, (planet1, longitude1) in enumerate(planet_items):
        for planet2, longitude2 in planet_items[i + 1:]:
            angle = abs(longitude1 - longitude2)
            angle = min(angle, 360 - angle)

            for aspect_name, aspect_angle in ASPECTS.items():
                orb = abs(angle - aspect_angle)

                if orb <= ASPECT_ORB:
                    aspects.append({
                        "planet1": planet1,
                        "planet2": planet2,
                        "aspect": aspect_name,
                        "angle": angle,
                        "orb": orb,
                    })
                    break

    return aspects