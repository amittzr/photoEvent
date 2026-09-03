"""Admin router for bulk photo uploads."""
import logging
import os
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.core.config import settings
from app.deps import AdminDep, SessionDep, get_upload_service
from app.models.folder import Folder
from app.models.upload_job import JobStatus, UploadJob
from app.repositories.event_repository import EventRepository
from app.repositories.folder_repository import FolderRepository
from app.schemas.job import DriveSyncRequest, UploadJobOut
from app.schemas.photo import PhotoOut, UploadResult
from app.services.drive_sync_service import sync_drive_folder_job
from app.services.drive_zip_service import process_drive_zip_job
from app.services.upload_service import UploadService
from app.services.zip_upload_service import process_zip_job

router = APIRouter(prefix="/api/admin", tags=["admin:photos"])
log = logging.getLogger("zip_upload")

UploadServiceDep = Annotated[UploadService, Depends(get_upload_service)]

# Accepted image content types for uploads.
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.post(
    "/folders/{folder_id}/photos",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photos(
    _: AdminDep,
    folder_id: uuid.UUID,
    session: SessionDep,
    service: UploadServiceDep,
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File(...)],
) -> UploadResult:
    """Bulk-upload images to a folder. Face indexing runs in the background."""
    folder = FolderRepository(session).get(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found.")
    event = EventRepository(session).get(folder.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    uploaded: list[PhotoOut] = []
    for file in files:
        if file.content_type not in _ALLOWED_TYPES:
            # Skip unsupported files rather than failing the whole batch.
            continue
        image_bytes = await file.read()
        ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"

        photo = service.upload_photo(
            event_id=folder.event_id,
            folder_id=folder_id,
            image_bytes=image_bytes,
            content_type=file.content_type,
            original_ext=ext,
            event_title=event.title,
            folder_name=folder.name,
        )
        # Schedule asynchronous face extraction (non-blocking).
        background.add_task(
            UploadService.index_faces_task,
            photo.id,
            photo.event_id,
            photo.drive_original_id,
        )
        uploaded.append(PhotoOut.model_validate(photo))

    return UploadResult(uploaded=uploaded)


@router.post(
    "/events/{event_id}/upload-zip",
    response_model=UploadJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_zip(
    _: AdminDep,
    event_id: uuid.UUID,
    session: SessionDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    folder_id: uuid.UUID | None = None,
) -> UploadJobOut:
    """Accept a large .zip of images and process it asynchronously."""
    log.info("[upload_zip] received request event_id=%s filename=%s content_type=%s",
             event_id, file.filename, file.content_type)

    event = EventRepository(session).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    # Resolve the target folder: use the provided one or a default "Uploads".
    folder_repo = FolderRepository(session)
    if folder_id is not None:
        folder = folder_repo.get(folder_id)
        if not folder or folder.event_id != event_id:
            raise HTTPException(status_code=404, detail="Folder not found.")
    else:
        existing = [f for f in folder_repo.list_for_event(event_id) if f.name == "Uploads"]
        folder = existing[0] if existing else folder_repo.create(
            Folder(event_id=event_id, name="Uploads")
        )

    # Create a unique working directory and stream the upload to disk.
    # Fall back to the system temp dir if the configured path isn't writable
    # (e.g. Render instance without a persistent disk mounted).
    job_id = uuid.uuid4()
    import tempfile

    base_tmp = settings.ZIP_TMP_DIR
    log.info("[upload_zip] configured ZIP_TMP_DIR=%s", base_tmp)
    try:
        os.makedirs(base_tmp, exist_ok=True)
        log.info("[upload_zip] using configured tmp dir: %s", base_tmp)
    except OSError as e:
        log.warning("[upload_zip] can't create %s (%s) — falling back to system tmp", base_tmp, e)
        base_tmp = tempfile.gettempdir()
    work_dir = os.path.join(base_tmp, str(job_id))
    os.makedirs(work_dir, exist_ok=True)
    zip_path = os.path.join(work_dir, "upload.zip")
    log.info("[upload_zip] work_dir=%s zip_path=%s", work_dir, zip_path)

    # Stream in chunks so multi-GB archives never sit fully in memory.
    bytes_written = 0
    log.info("[upload_zip] starting stream to disk: %s", zip_path)
    with open(zip_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB
            if not chunk:
                break
            out.write(chunk)
            bytes_written += len(chunk)
    log.info("[upload_zip] stream complete: %d bytes written to %s", bytes_written, zip_path)

    # Persist the job as PENDING.
    job = UploadJob(
        id=job_id,
        event_id=event_id,
        folder_id=folder.id,
        status=JobStatus.PENDING,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    log.info("[upload_zip] job created id=%s — scheduling background task", job_id)

    # Schedule background processing (extract + parallel workers).
    background.add_task(process_zip_job, job_id, zip_path, work_dir)
    log.info("[upload_zip] background task scheduled — returning 202")

    return UploadJobOut.model_validate(job)


@router.post(
    "/events/{event_id}/upload-zip-from-drive",
    response_model=UploadJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_zip_from_drive(
    _: AdminDep,
    event_id: uuid.UUID,
    session: SessionDep,
    background: BackgroundTasks,
    drive_file_id: str,
    folder_id: uuid.UUID | None = None,
) -> UploadJobOut:
    """Process a .zip stored in Google Drive without any HTTP upload.

    The user uploads their ZIP to Google Drive and provides its file ID here.
    The server downloads the ZIP directly from Drive (no request timeout) then
    processes it exactly like a direct ZIP upload. This is the recommended path
    for large archives on Render's free tier.
    """
    import tempfile

    event = EventRepository(session).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    folder_repo = FolderRepository(session)
    if folder_id is not None:
        folder = folder_repo.get(folder_id)
        if not folder or folder.event_id != event_id:
            raise HTTPException(status_code=404, detail="Folder not found.")
    else:
        existing = [f for f in folder_repo.list_for_event(event_id) if f.name == "Uploads"]
        folder = existing[0] if existing else folder_repo.create(
            Folder(event_id=event_id, name="Uploads")
        )

    job_id = uuid.uuid4()
    base_tmp = settings.ZIP_TMP_DIR
    try:
        os.makedirs(base_tmp, exist_ok=True)
    except OSError:
        base_tmp = tempfile.gettempdir()
    work_dir = os.path.join(base_tmp, str(job_id))
    os.makedirs(work_dir, exist_ok=True)

    job = UploadJob(
        id=job_id,
        event_id=event_id,
        folder_id=folder.id,
        status=JobStatus.PENDING,
        message=f"Queued: will download ZIP from Drive file {drive_file_id}",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    background.add_task(process_drive_zip_job, job_id, drive_file_id, work_dir)
    log.info("[upload_zip_from_drive] job=%s drive_file_id=%s", job_id, drive_file_id)
    return UploadJobOut.model_validate(job)


def _resolve_import_folder(
    session, event_id: uuid.UUID, target_folder_id: uuid.UUID | None
):
    """Resolve the sub-folder photos are attached to for a Drive sync.

    Uses the provided target folder, or gets/creates a default "Drive Import".
    """
    folder_repo = FolderRepository(session)
    if target_folder_id is not None:
        folder = folder_repo.get(target_folder_id)
        if not folder or folder.event_id != event_id:
            raise HTTPException(status_code=404, detail="Target folder not found.")
        return folder
    existing = [
        f for f in folder_repo.list_for_event(event_id) if f.name == "Drive Import"
    ]
    return existing[0] if existing else folder_repo.create(
        Folder(event_id=event_id, name="Drive Import")
    )


@router.post(
    "/events/{event_id}/sync",
    response_model=UploadJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_drive_folder(
    _: AdminDep,
    event_id: uuid.UUID,
    session: SessionDep,
    background: BackgroundTasks,
    body: DriveSyncRequest | None = None,
) -> UploadJobOut:
    """Ingest photos from a linked Google Drive folder into this event.

    Uses the folder ID from the request body if given, otherwise the event's
    stored drive_folder_id. Runs in the background and returns 202 with a job to
    poll. Already-imported files (by Drive file ID) are skipped.
    """
    event = EventRepository(session).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    body = body or DriveSyncRequest()
    drive_folder_id = body.drive_folder_id or event.drive_folder_id
    if not drive_folder_id:
        raise HTTPException(
            status_code=400,
            detail="No Drive folder ID provided or stored on the event.",
        )

    # Persist the folder id on the event if it was supplied ad hoc.
    if body.drive_folder_id and body.drive_folder_id != event.drive_folder_id:
        event.drive_folder_id = body.drive_folder_id
        session.add(event)
        session.commit()

    folder = _resolve_import_folder(session, event_id, body.target_folder_id)

    job = UploadJob(event_id=event_id, folder_id=folder.id, status=JobStatus.PENDING)
    session.add(job)
    session.commit()
    session.refresh(job)

    background.add_task(sync_drive_folder_job, job.id, drive_folder_id)
    return UploadJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=UploadJobOut)
def get_job(_: AdminDep, job_id: uuid.UUID, session: SessionDep) -> UploadJobOut:
    """Return the current status/progress of a bulk upload job."""
    job = session.get(UploadJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return UploadJobOut.model_validate(job)
