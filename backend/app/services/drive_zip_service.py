"""Process a ZIP file stored in Google Drive.

The user uploads a ZIP to their own Drive and provides the file ID.
The server downloads it server-side (no HTTP request timeout) and
processes it exactly like a direct ZIP upload.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid

from app.core.config import settings
from app.core.database import engine
from app.models.upload_job import JobStatus, UploadJob
from app.services.storage_service import StorageService
from app.services.zip_upload_service import process_zip_job
from sqlmodel import Session
from datetime import datetime, timezone

log = logging.getLogger("drive_zip")


def _touch_job(session, job) -> None:
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def process_drive_zip_job(job_id: uuid.UUID, drive_file_id: str, work_dir: str) -> None:
    """Background entrypoint: download ZIP from Drive then hand off to process_zip_job."""
    log.info("[drive_zip job=%s] starting — drive_file_id=%s work_dir=%s",
             job_id, drive_file_id, work_dir)

    with Session(engine) as session:
        job = session.get(UploadJob, job_id)
        if not job:
            log.error("[drive_zip job=%s] job row not found", job_id)
            return
        job.status = JobStatus.PROCESSING
        job.message = "Downloading ZIP from Google Drive..."
        _touch_job(session, job)

    zip_path = os.path.join(work_dir, "upload.zip")
    try:
        os.makedirs(work_dir, exist_ok=True)
        log.info("[drive_zip job=%s] downloading ZIP from Drive", job_id)
        storage = StorageService()
        zip_bytes = storage.get_file_stream(drive_file_id)
        with open(zip_path, "wb") as fh:
            fh.write(zip_bytes)
        log.info("[drive_zip job=%s] downloaded %d bytes", job_id, len(zip_bytes))
    except Exception as exc:
        log.exception("[drive_zip job=%s] download failed: %s", job_id, exc)
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.message = f"Download from Drive failed: {exc}"
                _touch_job(session, job)
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    # Hand off to the existing ZIP processing pipeline.
    process_zip_job(job_id, zip_path, work_dir)
