"""Streaming ZIP bulk-upload processing with parallel background workers.

Flow:
1. The router streams the uploaded .zip to a temp file on disk (never fully in RAM).
2. A background task extracts entries one by one, filtering junk/non-image files.
3. A ThreadPoolExecutor processes images in parallel: generate WebP thumbnail,
   upload the original to Drive, extract face embeddings, persist rows.
4. The UploadJob row is updated with progress; temp files are cleaned up.
"""
from __future__ import annotations

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
from app.models.face import Face
from app.models.folder import Folder
from app.models.photo import Photo, PhotoStatus
from app.models.upload_job import JobStatus, UploadJob
from app.services.drive_paths import build_object_path
from app.services.face_service import FaceService
from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService

# Allowed image extensions inside the archive.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".gif"}

# Content types by extension for the Drive upload.
_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}


def _is_valid_image_entry(name: str) -> bool:
    """Filter out directories, hidden/system files, and non-images."""
    base = os.path.basename(name)
    if not base or name.endswith("/"):
        return False
    # Skip macOS resource forks and hidden/system files.
    if "__MACOSX" in name or base.startswith(".") or base.startswith("._"):
        return False
    ext = os.path.splitext(base)[1].lower()
    return ext in _IMAGE_EXTS


def _touch_job(session: Session, job: UploadJob) -> None:
    """Persist job progress with an updated timestamp."""
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
    """Process a single extracted image end to end.

    Each call uses its own DB session and Drive/Thumbnail/Face services so it is
    safe to run inside a worker thread. Returns True on success.
    """
    photo_id = uuid.uuid4()
    ext = os.path.splitext(file_path)[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

    try:
        with open(file_path, "rb") as fh:
            image_bytes = fh.read()

        # 1) Local WebP thumbnail.
        thumbnails = ThumbnailService()
        width, height = thumbnails.generate(image_bytes, photo_id)

        # 2) Upload original to Drive under a readable event/category folder path.
        storage = StorageService()
        original_path = build_object_path(
            event_id, event_title, folder_name, photo_id, ext
        )
        original_id = storage.upload_bytes(image_bytes, original_path, content_type)

        # 3) Persist the photo row.
        with Session(engine) as session:
            photo = Photo(
                id=photo_id,
                folder_id=folder_id,
                event_id=event_id,
                drive_original_id=original_id,
                drive_thumb_id=None,
                original_url=storage.get_public_url(original_id),
                thumb_url=f"/api/public/photos/{photo_id}/thumbnail",
                width=width,
                height=height,
                status=PhotoStatus.PROCESSING,
            )
            session.add(photo)
            session.commit()

        # 4) Extract face embeddings and persist them.
        detected = FaceService().extract_faces(image_bytes)
        with Session(engine) as session:
            faces = [
                Face(
                    photo_id=photo_id,
                    event_id=event_id,
                    embedding=d.embedding,
                    bbox=d.bbox,
                    det_score=d.det_score,
                )
                for d in detected
            ]
            if faces:
                session.add_all(faces)
            db_photo = session.get(Photo, photo_id)
            if db_photo:
                db_photo.status = PhotoStatus.DONE
                session.add(db_photo)
            session.commit()
        return True
    except Exception:
        # Best-effort: mark the photo failed if it was created.
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
        # 5) Clean up the extracted temp file.
        try:
            os.remove(file_path)
        except OSError:
            pass


def process_zip_job(job_id: uuid.UUID, zip_path: str, work_dir: str) -> None:
    """Background entrypoint: extract the ZIP and process images in parallel."""
    with Session(engine) as session:
        job = session.get(UploadJob, job_id)
        if not job:
            return
        event_id = job.event_id
        folder_id = job.folder_id
        # Resolve readable names for the Drive folder path.
        event = session.get(Event, event_id)
        folder = session.get(Folder, folder_id)
        event_title = event.title if event else "event"
        folder_name = folder.name if folder else "Photos"
        job.status = JobStatus.PROCESSING
        _touch_job(session, job)

    extract_dir = os.path.join(work_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    extracted_files: list[str] = []
    try:
        # Extract valid image entries one at a time (streamed, not all in RAM).
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if not _is_valid_image_entry(info.filename):
                    continue
                # Flatten to a unique name to avoid nested-path collisions.
                safe_name = f"{uuid.uuid4().hex}{os.path.splitext(info.filename)[1].lower()}"
                dest = os.path.join(extract_dir, safe_name)
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                extracted_files.append(dest)

        # Record the total count now that we know it.
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.total = len(extracted_files)
                _touch_job(session, job)

        # Process images in parallel with a bounded thread pool.
        processed = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=settings.ZIP_MAX_WORKERS) as pool:
            futures = [
                pool.submit(
                    _process_one_image,
                    path,
                    event_id,
                    folder_id,
                    event_title,
                    folder_name,
                )
                for path in extracted_files
            ]
            for future in as_completed(futures):
                ok = future.result()
                if ok:
                    processed += 1
                else:
                    failed += 1
                # Update progress periodically (every image is fine at this scale).
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
                job.message = f"Processed {processed} image(s), {failed} failed."
                _touch_job(session, job)
    except Exception as exc:
        with Session(engine) as session:
            job = session.get(UploadJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.message = f"ZIP processing failed: {exc}"
                _touch_job(session, job)
    finally:
        # Clean up the temp working directory and the uploaded ZIP.
        shutil.rmtree(work_dir, ignore_errors=True)
