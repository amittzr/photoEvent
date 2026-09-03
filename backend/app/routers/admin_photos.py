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
from app.schemas.job import UploadJobOut
from app.schemas.photo import PhotoOut, UploadResult
from app.services.drive_sync_service import sync_drive_folder_job
from app.services.drive_zip_service import process_drive_zip_job
from app.services.upload_service import UploadService
from app.services.zip_upload_service import process_zip_job

router = APIRouter(prefix="/api/admin", tags=["admin:photos"])
log = logging.getLogger("admin_photos")

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
    """Accept a large .zip of images and process it asynchronously.

    The ZIP is streamed to disk (never fully loaded into RAM), a job row is
    created, and processing is scheduled in the background. Returns 202 with the
    job so the client can poll progress and the HTTP connection doesn't time out.
    """
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
    job_id = uuid.uuid4()
    work_dir = os.path.join(settings.ZIP_TMP_DIR, str(job_id))
    os.makedirs(work_dir, exist_ok=True)
    zip_path = os.path.join(work_dir, "upload.zip")

    # Stream in chunks so multi-GB archives never sit fully in memory.
    with open(zip_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB
            if not chunk:
                break
            out.write(chunk)

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

    # Schedule background processing (extract + parallel workers).
    background.add_task(process_zip_job, job_id, zip_path, work_dir)

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
    """Process a ZIP already in Google Drive — no HTTP upload, no timeout.

    Upload your ZIP to Google Drive, get its file ID, and pass it here.
    The server downloads the ZIP directly from Drive and processes it
    exactly like a local ZIP upload.
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
        existing = [f for f in folder_repo.list_for_event(event_id)
                    if f.name == "Uploads"]
        folder = existing[0] if existing else folder_repo.create(
            Folder(event_id=event_id, name="Uploads")
        )

    base_tmp = settings.ZIP_TMP_DIR
    try:
        os.makedirs(base_tmp, exist_ok=True)
    except OSError:
        base_tmp = tempfile.gettempdir()

    job_id = uuid.uuid4()
    work_dir = os.path.join(base_tmp, str(job_id))
    os.makedirs(work_dir, exist_ok=True)

    job = UploadJob(
        id=job_id,
        event_id=event_id,
        folder_id=folder.id,
        status=JobStatus.PENDING,
        message=f"Queued: downloading ZIP from Drive file {drive_file_id}",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    background.add_task(process_drive_zip_job, job_id, drive_file_id, work_dir)
    log.info("[upload_zip_from_drive] job=%s drive_file_id=%s", job_id, drive_file_id)
    return UploadJobOut.model_validate(job)


@router.post(
    "/events/{event_id}/sync-folder",
    response_model=UploadJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_drive_folder(
    _: AdminDep,
    event_id: uuid.UUID,
    session: SessionDep,
    background: BackgroundTasks,
    drive_folder_id: str,
    folder_id: uuid.UUID | None = None,
) -> UploadJobOut:
    """Ingest photos from an existing Google Drive folder one at a time.

    Processes each image sequentially (max_workers=1) so RAM never spikes —
    safe on Render's free 512MB tier. Already-imported files are skipped.
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
        existing = [f for f in folder_repo.list_for_event(event_id)
                    if f.name == "Drive Import"]
        folder = existing[0] if existing else folder_repo.create(
            Folder(event_id=event_id, name="Drive Import")
        )

    job = UploadJob(
        event_id=event_id,
        folder_id=folder.id,
        status=JobStatus.PENDING,
        message=f"Queued: will scan Drive folder {drive_folder_id}",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    background.add_task(sync_drive_folder_job, job.id, drive_folder_id)
    log.info("[sync_drive] job=%s folder=%s", job.id, drive_folder_id)
    return UploadJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=UploadJobOut)
def get_job(_: AdminDep, job_id: uuid.UUID, session: SessionDep) -> UploadJobOut:
    """Return the current status/progress of a bulk upload job."""
    job = session.get(UploadJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return UploadJobOut.model_validate(job)
