from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from astrology.analysis import analyze_chart
from astrology.calculator import calculate_chart
from astrology.interpreter import interpret_chart
from db.database import get_db
from db.models import Pet, User
from schemas.chart import ChartRequest


router = APIRouter(
    prefix="/api/charts",
    tags=["charts"],
)


@router.post("")
def create_chart(
    request: ChartRequest,
    db: Session = Depends(get_db),
):
    pet = Pet(
        pet_name=request.pet_name,
        pet_type=request.pet_type,
        pet_gender=request.pet_gender,
        pet_breed=request.pet_breed,
        pet_birth_date=request.pet_birth_date,
        pet_birth_time=request.pet_birth_time,
        city=request.city,
    )
    db.add(pet)
    db.flush()

    user = User(
        pet_id=pet.pet_id,
        user_name=request.user_name,
        user_email=request.user_email,
    )
    db.add(user)

    chart = calculate_chart(
        birth_date=request.pet_birth_date,
        birth_time=request.pet_birth_time,
        birth_place=request.city,
    )
    analysis = analyze_chart(chart)

    interpretation = interpret_chart(
        pet_name=request.pet_name,
        pet_type=request.pet_type,
        pet_breed=request.pet_breed,
        pet_gender=request.pet_gender,
        chart=chart,
        analysis=analysis,
    )

    db.commit()

    return {
        "user_id": user.user_id,
        "pet_id": pet.pet_id,
        "interpretation": interpretation,
        "analysis": analysis,
        "chart": chart,
    }