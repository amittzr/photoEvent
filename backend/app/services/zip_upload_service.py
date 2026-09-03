"""Streaming ZIP bulk-upload processing with parallel background workers."""
from __future__ import annotations

import logging
import os
import shutil
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.models.event import Event
from app.models.folder import Folder
from app.models.photo import Photo, PhotoStatus
from app.models.upload_job import JobStatus, UploadJob
from app.services.drive_paths import build_object_path
from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService

log = logging.getLogger("zip_upload")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".gif"}
_CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".bmp": "image/bmp", ".gif": "image/gif",
}


def _is_valid_image_entry(name: str) -> bool:
    base = os.path.basename(name)
    if not base or name.endswith("/"):
        return False
    if "__MACOSX" in name or base.startswith(".") or base.startswith("._"):
        return False
    return os.path.splitext(base)[1].lower() in _IMAGE_EXTS


def _touch_job(session: Session, job: UploadJob) -> None:
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()


def _process_one_image(
    file_path: str,
    event_id: uuid.UUID,
    folder_id: uuid.UUID,
    event_title: str,
    folder_name: str,
) -> bool:
    photo_id = uuid.uuid4()
    ext = os.path.splitext(file_path)[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    fname = os.path.basename(file_path)

    try:
        log.info("[worker] reading %s (ext=%s)", fname, ext)
        with open(file_path, "rb") as fh:
            image_bytes = fh.read()
        log.info("[worker] %s bytes read — generating thumbnail", len(image_bytes))

        thumbnails = ThumbnailService()
        width, height = thumbnails.generate(image_bytes, photo_id)
        log.info("[worker] thumbnail done (%dx%d) — uploading to Drive", width, height)

        storage = StorageService()
        original_path = build_object_path(event_id, event_title, folder_name, photo_id, ext)
        original_id = storage.upload_bytes(image_bytes, original_path, content_type)
        log.info("[worker] Drive upload done id=%s — saving photo row", original_id[:12])

        with Session(engine) as session:
            photo = Photo(
                id=photo_id, folder_id=folder_id, event_id=event_id,
                drive_original_id=original_id, drive_thumb_id=None,
                original_url=storage.get_public_url(original_id),
                thumb_url=f"/api/public/photos/{photo_id}/thumbnail",
                width=width, height=height,
                # Mark DONE immediately — face indexing skipped in bulk mode
                # to avoid OOM on memory-constrained servers (InsightFace ~400MB).
                status=PhotoStatus.DONE,
            )
            session.add(photo)
            session.commit()
        log.info("[worker] DONE for %s (faces skipped in bulk mode)", fname)
        return True

    except Exception:
        log.exception("[worker] FAILED for %s", fname)
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
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass


def process_zip_job(job_id: uuid.UUID, zip_path: str, work_dir: str) -> None:
    """Background entrypoint: extract the ZIP and process images in parallel."""
    log.info("[job %s] starting — zip=%s work_dir=%s", job_id, zip_path, work_dir)
    log.info("[job %s] zip size on disk: %s bytes",
             job_id, os.path.getsize(zip_path) if os.path.exists(zip_path) else "MISSING")

    with Session(engine) as session:
        job = session.get(UploadJob, job_id)
        if not job:
            log.error("[job %s] job row not found — aborting", job_id)
            return
        event_id = job.event_id
        folder_id = job.folder_id
        event = session.get(Event, event_id)
        folder = session.get(Folder, folder_id)
        event_title = event.title if event else "event"
        folder_name = folder.name if folder else "Photos"
        job.status = JobStatus.PROCESSING
        _touch_job(session, job)
    log.info("[job %s] event='%s' folder='%s'", job_id, event_title, folder_name)

    extract_dir = os.path.join(work_dir, "extracted")
    log.info("[job %s] creating extract dir: %s", job_id, extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    extracted_files: list[str] = []
    try:
        log.info("[job %s] opening ZIP for extraction", job_id)
        with zipfile.ZipFile(zip_path) as zf:
            all_entries = zf.infolist()
            log.info("[job %s] ZIP has %d total entries", job_id, len(all_entries))
            for info in all_entries:
                if not _is_valid_image_entry(info.filename):
                    log.debug("[job %s] skipping %s", job_id, info.filename)
                    continue
                safe_name = f"{uuid.uuid4().hex}{os.path.splitext(info.filename)[1].lower()}"
                dest = os.path.join(extract_dir, safe_name)
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                extracted_files.append(dest)
        log.info("[job %s] extracted %d valid image(s)", job_id, len(extracted_files))

        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.total = len(extracted_files)
                _touch_job(session, job)

        if not extracted_files:
            log.warning("[job %s] no images found in ZIP — marking done", job_id)
            with Session(engine) as session:
                job = session.get(UploadJob, job_id)
                if job:
                    job.status = JobStatus.DONE
                    job.message = "No valid images found in ZIP."
                    _touch_job(session, job)
            return

        processed = 0
        failed = 0
        log.info("[job %s] starting ThreadPoolExecutor max_workers=%d",
                 job_id, settings.ZIP_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=settings.ZIP_MAX_WORKERS) as pool:
            futures = [
                pool.submit(_process_one_image, path, event_id, folder_id,
                            event_title, folder_name)
                for path in extracted_files
            ]
            for future in as_completed(futures):
                try:
                    ok = future.result()
                except Exception:
                    log.exception("[job %s] future raised unexpectedly", job_id)
                    ok = False
                if ok:
                    processed += 1
                else:
                    failed += 1
                log.info("[job %s] progress: %d/%d done, %d failed",
                         job_id, processed + failed, len(extracted_files), failed)
                with Session(engine) as session:
                    job = session.get(UploadJob, job_id)
                    if job:
                        job.processed = processed
                        job.failed = failed
                        _touch_job(session, job)

        log.info("[job %s] all workers finished: %d ok, %d failed", job_id, processed, failed)
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.DONE
                job.message = f"Processed {processed} image(s), {failed} failed."
                _touch_job(session, job)

    except Exception as exc:
        log.exception("[job %s] top-level failure: %s", job_id, exc)
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.message = f"ZIP processing failed: {exc}"
                _touch_job(session, job)
    finally:
        log.info("[job %s] cleaning up work_dir", job_id)
        shutil.rmtree(work_dir, ignore_errors=True)
