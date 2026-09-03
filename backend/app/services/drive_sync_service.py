"""Ingest existing Google Drive photos into the database.

Given a Drive folder ID, this lists every image already in that folder,
skips ones already imported (by Drive file ID), and for each new file:

1. Downloads the bytes from Drive.
2. Generates + caches a local WebP thumbnail.
3. Creates a Photo row referencing the EXISTING Drive file (no re-upload).
4. Extracts face embeddings into pgvector.

Progress is tracked on an UploadJob row, and work is parallelized with a
bounded ThreadPoolExecutor. Originals are NOT re-uploaded or duplicated: the
Photo.drive_original_id points at the file already living in Drive.
"""
from __future__ import annotations

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


def _touch_job(session: Session, job: UploadJob) -> None:
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _ingest_one(
    drive_file_id: str,
    event_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> bool:
    """Ingest a single existing Drive file into the DB. Returns True on success."""
    photo_id = uuid.uuid4()
    try:
        storage = StorageService()
        image_bytes = storage.get_file_stream(drive_file_id)

        # Ensure the file is publicly readable (needed for the download proxy).
        try:
            storage._grant_public_read(drive_file_id)  # noqa: SLF001
        except Exception:
            # Non-fatal: proxy streaming works regardless of public permission.
            pass

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
                session.add_all(
                    [
                        Face(
                            photo_id=photo_id,
                            event_id=event_id,
                            embedding=d.embedding,
                            bbox=d.bbox,
                            det_score=d.det_score,
                        )
                        for d in detected
                    ]
                )
            db_photo = session.get(Photo, photo_id)
            if db_photo:
                db_photo.status = PhotoStatus.DONE
                session.add(db_photo)
            session.commit()
        return True
    except Exception:
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


def sync_drive_folder_job(
    job_id: uuid.UUID, drive_folder_id: str
) -> None:
    """Background entrypoint: enumerate a Drive folder and ingest new images."""
    with Session(engine) as session:
        job = session.get(UploadJob, job_id)
        if not job:
            return
        event_id = job.event_id
        folder_id = job.folder_id
        job.status = JobStatus.PROCESSING
        _touch_job(session, job)

    try:
        storage = StorageService()
        drive_files = storage.list_image_files(drive_folder_id)

        # Skip files already ingested for this event (dedupe on Drive file ID).
        with Session(engine) as session:
            existing = PhotoRepository(session).existing_drive_ids_for_event(event_id)
        new_files = [f for f in drive_files if f["id"] not in existing]

        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.total = len(new_files)
                job.message = (
                    f"Found {len(drive_files)} image(s); "
                    f"{len(new_files)} new to import."
                )
                _touch_job(session, job)

        processed = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=settings.ZIP_MAX_WORKERS) as pool:
            futures = [
                pool.submit(_ingest_one, f["id"], event_id, folder_id)
                for f in new_files
            ]
            for future in as_completed(futures):
                if future.result():
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
                job.message = (
                    f"Imported {processed} new photo(s), {failed} failed."
                )
                _touch_job(session, job)
    except Exception as exc:
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.message = f"Drive sync failed: {exc}"
                _touch_job(session, job)
