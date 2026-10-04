from datetime import date, time

from pydantic import BaseModel, EmailStr


class ChartRequest(BaseModel):
    user_name: str
    user_email: EmailStr

    pet_name: str
    pet_type: str
    pet_gender: str
    pet_breed: str

    pet_birth_date: date
    pet_birth_time: time | None = None
    city: str