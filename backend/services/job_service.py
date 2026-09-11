# backend/services/job_service.py
import uuid
from datetime import datetime, timezone
from typing import Callable, Any

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import BackgroundJob, JobStatus


def create_job(db: Session, user_id: int, job_type: str) -> BackgroundJob:
    job = BackgroundJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_type=job_type,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str, user_id: int) -> BackgroundJob | None:
    return (
        db.query(BackgroundJob)
        .filter(BackgroundJob.id == job_id, BackgroundJob.user_id == user_id)
        .first()
    )


def run_job(job_id: str, task: Callable[[Session], Any]) -> None:
    """
    Executes *task(db)* in a background thread with its own DB session.
    The task receives the session so it can do DB work without reusing
    the closed request-scoped session.
    Updates the job row to running → completed/failed.
    """
    db: Session = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job is None:
            return

        job.status = JobStatus.RUNNING
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        result = task(db)

        job.status = JobStatus.COMPLETED
        job.result = result
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
