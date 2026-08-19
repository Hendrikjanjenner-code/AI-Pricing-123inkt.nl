"""Status-endpoint voor achtergrond-engine-runs (zie services/engine_jobs)."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
import models
from services.engine_jobs import get_engine_job

router = APIRouter(prefix="/api/engine-jobs", tags=["engine-jobs"])


@router.get("/{job_id}")
def engine_job_status(
    job_id: str,
    _: models.User = Depends(get_current_user),
) -> Any:
    job = get_engine_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Onbekende of verlopen job. Start de herberekening opnieuw.",
        )
    return job
