# backend/api/endpoints/jobs.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.endpoints.auth import get_current_user
from core.database import get_db
from models.database import User
from models.schemas import JobStatusResponse  # noqa: F401 (response_model uses string ref)
from services.job_service import get_job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll the status of a background job. Returns result when completed or error when failed."""
    job = get_job(db, job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse.from_orm_job(job)
