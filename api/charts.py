import logging
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import APIError
from sqlalchemy.orm import Session

from astrology.analysis import analyze_chart
from astrology.calculator import calculate_chart
from astrology.compatibility import analyze_compatibility
from services.interpreter import (
    interpret_human, interpret_pet, interpret_compatibility, prepare_chart_for_ai,
)
from core.limiter import limiter
from db.database import get_db
from db.models import Pet, User
from schemas.chart import HumanChartRequest, CompatibilityChartRequest


logger = logging.getLogger(__name__)
timing_logger = logging.getLogger("uvicorn.error.chart_timing")


@contextmanager
def measure_compatibility_step(timings: dict[str, float], step: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[step] = timings.get(step, 0.0) + time.perf_counter() - started



def timed_interpretation(timings: dict[str, float], step: str, interpret, **kwargs):
    with measure_compatibility_step(timings, step):
        return interpret(**kwargs)



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


@router.post("/humans")
@limiter.limit("5/minute")
def create_human_chart(
    request: Request,
    payload: HumanChartRequest,
    db: Session = Depends(get_db),
):
    request_started = time.perf_counter()
    timings: dict[str, float] = {}
    stage = "database"
    try:
        with measure_compatibility_step(timings, "db_save_commit"):
            user = User(
                user_name=payload.user_name,
                user_email=payload.user_email,
                user_birth_date=payload.user_birth_date,
                user_birth_time=payload.user_birth_time,
                user_city=payload.user_city,
            )
            db.add(user)
            db.flush()
        stage = "calculation"
        with measure_compatibility_step(timings, "human_chart_calculation"):
            human_chart = calculate_chart(
                birth_date=payload.user_birth_date,
                birth_time=payload.user_birth_time,
                birth_place=payload.user_city,
            )
            stage = "analysis"
            human_analysis = analyze_chart(human_chart)
        stage = "interpretation"
        with measure_compatibility_step(timings, "human_gpt_interpretation"):
            human_interpretation = interpret_human(
                user_name=payload.user_name,
                chart=human_chart,
                analysis=human_analysis,
            )
        stage = "database"
        with measure_compatibility_step(timings, "db_save_commit"):
            result = {
                "user_id": user.user_id,
                "interpretation": human_interpretation,
                "analysis": human_analysis,
                "chart": human_chart,
            }
            db.commit()
        return result
    except APIError:
        with measure_compatibility_step(timings, "db_save_commit"):
            rollback_transaction(db)
        # SDK exception bodies can contain request data and provider internals.
        logger.warning("Chart request failed: OpenAI service error; stage=%s", stage)
        raise HTTPException(
            status_code=503,
            detail="AI interpretation service is temporarily unavailable.",
        ) from None
    except Exception:
        with measure_compatibility_step(timings, "db_save_commit"):
            rollback_transaction(db)
        logger.error("Chart request failed: internal error; stage=%s", stage)
        raise HTTPException(
            status_code=500,
            detail="Unable to create chart. Please try again later.",
        ) from None
    finally:
        total_seconds = time.perf_counter() - request_started
        for step, seconds in timings.items():
            timing_logger.info(
                "human_timing step=%s elapsed_seconds=%.6f", step, seconds,
            )
        timing_logger.info(
            "human_timing step=api_total elapsed_seconds=%.6f", total_seconds,
        )


@router.post("/compatibility")
@limiter.limit("5/minute")
def create_compatibility_chart(
    request: Request,
    payload: CompatibilityChartRequest,
    db: Session = Depends(get_db),
):
    request_started = time.perf_counter()
    timings: dict[str, float] = {}
    stage = "database"
    try:
        with measure_compatibility_step(timings, "db_save_commit"):
            user = User(
                user_name=payload.user_name,
                user_email=payload.user_email,
                user_birth_date=payload.user_birth_date,
                user_birth_time=payload.user_birth_time,
                user_city=payload.user_city,
            )
            db.add(user)
            db.flush()
            pet = Pet(
                user_id=user.user_id,
                pet_name=payload.pet_name,
                pet_type=payload.pet_type,
                pet_gender=payload.pet_gender,
                pet_breed=payload.pet_breed,
                pet_birth_date=payload.pet_birth_date,
                pet_birth_time=payload.pet_birth_time,
                pet_city=payload.pet_city,
            )
            db.add(pet)
        stage = "calculation"
        with measure_compatibility_step(timings, "human_chart_calculation"):
            human_chart = calculate_chart(
                birth_date=payload.user_birth_date,
                birth_time=payload.user_birth_time,
                birth_place=payload.user_city,
            )
            stage = "analysis"
            human_analysis = analyze_chart(human_chart)
        stage = "interpretation"
        stage = "calculation"
        with measure_compatibility_step(timings, "pet_chart_calculation"):
            pet_chart = calculate_chart(
                birth_date=payload.pet_birth_date,
                birth_time=payload.pet_birth_time,
                birth_place=payload.pet_city,
            )
            stage = "analysis"
            pet_analysis = analyze_chart(pet_chart)
        stage = "interpretation"

        stage = "compatibility_analysis"
        with measure_compatibility_step(timings, "compatibility_calculation_analysis"):
            compatibility_analysis = analyze_compatibility(human_chart, pet_chart)
            human_prepared = prepare_chart_for_ai(human_chart, human_analysis)
            pet_prepared = prepare_chart_for_ai(pet_chart, pet_analysis)
        stage = "interpretation"
        # Only plain chart data enters workers; the Session stays on this thread.
        # Each worker owns its timing dictionary, merged after all workers stop.
        gpt_timings = [{}, {}, {}]
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                human_interpretation_future = executor.submit(
                    timed_interpretation, gpt_timings[0], "human_gpt_interpretation",
                    interpret_human,
                    user_name=payload.user_name,
                    chart=human_chart,
                    analysis=human_analysis,
                )
                pet_interpretation_future = executor.submit(
                    timed_interpretation, gpt_timings[1], "pet_gpt_interpretation",
                    interpret_pet,
                    pet_name=payload.pet_name,
                    pet_type=payload.pet_type,
                    pet_breed=payload.pet_breed,
                    pet_gender=payload.pet_gender,
                    chart=pet_chart,
                    analysis=pet_analysis,
                )
                compatibility_interpretation_future = executor.submit(
                    timed_interpretation, gpt_timings[2], "compatibility_gpt_interpretation",
                    interpret_compatibility,
                    human={
                        "name": payload.user_name,
                        "chart": human_prepared["chart"],
                        "analysis": human_prepared["analysis"],
                    },
                    pet={
                        "name": payload.pet_name,
                        "type": payload.pet_type,
                        "breed": payload.pet_breed,
                        "gender": payload.pet_gender,
                        "chart": pet_prepared["chart"],
                        "analysis": pet_prepared["analysis"],
                    },
                    compatibility_analysis=compatibility_analysis,
                )
                human_interpretation = human_interpretation_future.result()
                pet_interpretation = pet_interpretation_future.result()
                compatibility_interpretation = compatibility_interpretation_future.result()
        finally:
            for worker_timings in gpt_timings:
                timings.update(worker_timings)
        stage = "database"
        with measure_compatibility_step(timings, "db_save_commit"):
            db.flush()
            result = {
                "user_id": user.user_id,
                "pet_id": pet.pet_id,
                "human": {
                    "interpretation": human_interpretation,
                    "analysis": human_analysis,
                    "chart": human_chart,
                },
                "pet": {
                    "interpretation": pet_interpretation,
                    "analysis": pet_analysis,
                    "chart": pet_chart,
                },
                "compatibility": {
                    "interpretation": compatibility_interpretation,
                    "analysis": compatibility_analysis,
                },
            }
            db.commit()
        return result
    except APIError:
        with measure_compatibility_step(timings, "db_save_commit"):
            rollback_transaction(db)
        # SDK exception bodies can contain request data and provider internals.
        logger.warning("Chart request failed: OpenAI service error; stage=%s", stage)
        raise HTTPException(
            status_code=503,
            detail="AI interpretation service is temporarily unavailable.",
        ) from None
    except Exception:
        with measure_compatibility_step(timings, "db_save_commit"):
            rollback_transaction(db)
        logger.error("Chart request failed: internal error; stage=%s", stage)
        raise HTTPException(
            status_code=500,
            detail="Unable to create chart. Please try again later.",
        ) from None
    finally:
        total_seconds = time.perf_counter() - request_started
        for step, seconds in timings.items():
            timing_logger.info(
                "compatibility_timing step=%s elapsed_seconds=%.6f", step, seconds,
            )
        timing_logger.info(
            "compatibility_timing step=api_total elapsed_seconds=%.6f", total_seconds,
        )
