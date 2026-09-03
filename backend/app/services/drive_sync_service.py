"""Ingest existing Google Drive photos into the database one at a time.

Processes one image per worker call so peak RAM never exceeds one photo + the
dlib face model (~80MB total) — safe on Render's 512MB free tier.
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.models.face import Face
from app.models.photo import Photo, PhotoStatus
from app.models.upload_job import JobStatus, UploadJob
from app.repositories.photo_repository import PhotoRepository
from app.services.face_service import FaceService
from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService

log = logging.getLogger("drive_sync")


def _touch_job(session: Session, job: UploadJob) -> None:
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _ingest_one(
    drive_file_id: str,
    event_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> bool:
    """Download one Drive file, generate thumbnail, extract faces, persist."""
    photo_id = uuid.uuid4()
    try:
        storage = StorageService()
        # Stream single photo bytes — typically 2-8MB, safe for RAM.
        image_bytes = storage.get_file_stream(drive_file_id)

        thumbnails = ThumbnailService()
        width, height = thumbnails.generate(image_bytes, photo_id)

        with Session(engine) as session:
            photo = Photo(
                id=photo_id,
                folder_id=folder_id,
                event_id=event_id,
                drive_original_id=drive_file_id,
                drive_thumb_id=None,
                original_url=storage.get_public_url(drive_file_id),
                thumb_url=f"/api/public/photos/{photo_id}/thumbnail",
                width=width,
                height=height,
                status=PhotoStatus.PROCESSING,
            )
            session.add(photo)
            session.commit()

        detected = FaceService().extract_faces(image_bytes)
        with Session(engine) as session:
            if detected:
                session.add_all([
                    Face(photo_id=photo_id, event_id=event_id,
                         embedding=d.embedding, bbox=d.bbox, det_score=d.det_score)
                    for d in detected
                ])
            db_photo = session.get(Photo, photo_id)
            if db_photo:
                db_photo.status = PhotoStatus.DONE
                session.add(db_photo)
            session.commit()
        # Free image bytes explicitly.
        del image_bytes
        return True
    except Exception:
        log.exception("[sync] failed on drive_file_id=%s", drive_file_id)
        try:
            with Session(engine) as session:
                db_photo = session.get(Photo, photo_id)
                if db_photo:
                    db_photo.status = PhotoStatus.FAILED
                    session.add(db_photo)
                    session.commit()
        except Exception:
            pass
        return False


def sync_drive_folder_job(job_id: uuid.UUID, drive_folder_id: str) -> None:
    """Background: list all images in a Drive folder and ingest new ones."""
    log.info("[sync job=%s] starting folder=%s", job_id, drive_folder_id)

    with Session(engine) as session:
        job = session.get(UploadJob, job_id)
        if not job:
            return
        event_id = job.event_id
        folder_id = job.folder_id
        job.status = JobStatus.PROCESSING
        job.message = "Listing images in Drive folder..."
        _touch_job(session, job)

    try:
        storage = StorageService()
        all_files = storage.list_image_files(drive_folder_id)
        log.info("[sync job=%s] found %d images", job_id, len(all_files))

        # Skip files already imported for this event.
        with Session(engine) as session:
            existing = PhotoRepository(session).existing_drive_ids_for_event(event_id)
        new_files = [f for f in all_files if f["id"] not in existing]
        log.info("[sync job=%s] %d new to import", job_id, len(new_files))

        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.total = len(new_files)
                job.message = f"Found {len(all_files)} images, {len(new_files)} new."
                _touch_job(session, job)

        processed = 0
        failed = 0
        # max_workers=1 keeps peak RAM to one photo at a time — safest on free tier.
        # Increase to 2-3 only if you upgrade Render's instance type.
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = [
                pool.submit(_ingest_one, f["id"], event_id, folder_id)
                for f in new_files
            ]
            for future in as_completed(futures):
                ok = future.result()
                if ok:
                    processed += 1
                else:
                    failed += 1
                with Session(engine) as session:
                    job = session.get(UploadJob, job_id)
                    if job:
                        job.processed = processed
                        job.failed = failed
                        _touch_job(session, job)

        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.DONE
                job.message = f"Imported {processed} photo(s), {failed} failed."
                _touch_job(session, job)
        log.info("[sync job=%s] done %d ok %d failed", job_id, processed, failed)

    except Exception as exc:
        log.exception("[sync job=%s] failed: %s", job_id, exc)
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.message = f"Sync failed: {exc}"
                _touch_job(session, job)
