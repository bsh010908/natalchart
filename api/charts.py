import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import APIError
from sqlalchemy.orm import Session

from astrology.analysis import analyze_chart
from astrology.calculator import calculate_chart
from astrology.interpreter import interpret_chart
from core.limiter import limiter
from db.database import get_db
from db.models import Pet, User
from schemas.chart import ChartRequest


logger = logging.getLogger(__name__)


def rollback_transaction(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        # Do not log exception text: DB errors may contain SQL parameters.
        logger.error("Chart transaction rollback failed")


router = APIRouter(
    prefix="/api/charts",
    tags=["charts"],
)


@router.post("")
@limiter.limit("5/minute")
def create_chart(
    request: Request,
    payload: ChartRequest,
    db: Session = Depends(get_db),
):
    stage = "database"
    try:
        pet = Pet(
            pet_name=payload.pet_name,
            pet_type=payload.pet_type,
            pet_gender=payload.pet_gender,
            pet_breed=payload.pet_breed,
            pet_birth_date=payload.pet_birth_date,
            pet_birth_time=payload.pet_birth_time,
            city=payload.city,
        )
        db.add(pet)
        db.flush()

        user = User(
            pet_id=pet.pet_id,
            user_name=payload.user_name,
            user_email=payload.user_email,
        )
        db.add(user)

        stage = "calculation"
        chart = calculate_chart(
            birth_date=payload.pet_birth_date,
            birth_time=payload.pet_birth_time,
            birth_place=payload.city,
        )
        stage = "analysis"
        analysis = analyze_chart(chart)

        stage = "interpretation"
        interpretation = interpret_chart(
            pet_name=payload.pet_name,
            pet_type=payload.pet_type,
            pet_breed=payload.pet_breed,
            pet_gender=payload.pet_gender,
            chart=chart,
            analysis=analysis,
        )

        stage = "database"
        # Allocate user_id and capture IDs before commit expires ORM attributes.
        db.flush()
        result = {
            "user_id": user.user_id,
            "pet_id": pet.pet_id,
            "interpretation": interpretation,
            "analysis": analysis,
            "chart": chart,
        }

        db.commit()
        return result
    except APIError:
        rollback_transaction(db)
        # SDK exception bodies can contain request data and provider internals.
        logger.warning("Chart request failed: OpenAI service error; stage=%s", stage)
        raise HTTPException(
            status_code=503,
            detail="AI interpretation service is temporarily unavailable.",
        ) from None
    except Exception:
        rollback_transaction(db)
        logger.error("Chart request failed: internal error; stage=%s", stage)
        raise HTTPException(
            status_code=500,
            detail="Unable to create chart. Please try again later.",
        ) from None
