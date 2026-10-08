
from datetime import date, time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]

City = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
    ),
]

Breed = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=100,
    ),
]


class HumanChartRequest(BaseModel):
    user_name: Name
    user_email: Annotated[EmailStr, Field(max_length=255)]

    user_birth_date: date
    user_birth_time: time | None = None
    user_city: City

    @field_validator("user_email", mode="before")
    @classmethod
    def strip_email(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if len(value) > 255:
                raise ValueError(
                    "Email must be at most 255 characters"
                )
        return value

    @field_validator("user_birth_date")
    @classmethod
    def reject_future_birth_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError(
                "Birth date must not be in the future"
            )
        return value


class CompatibilityChartRequest(HumanChartRequest):
    pet_name: Name
    pet_type: Literal["dog", "cat", "other"]
    pet_gender: Literal["male", "female", "other"]
    pet_breed: Breed

    pet_birth_date: date
    pet_birth_time: time | None = None
    pet_city: City

    @field_validator("pet_birth_date")
    @classmethod
    def reject_future_pet_birth_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError(
                "Birth date must not be in the future"
            )
        return value
