"""Guest-facing public router: event view, selfie search, download."""
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse

from app.deps import (
    SessionDep,
    get_event_service,
    get_search_service,
    get_storage_service,
)
from app.repositories.photo_repository import PhotoRepository
from app.services.thumbnail_service import ThumbnailService
from app.schemas.event import EventDetailOut
from app.schemas.photo import PhotoOut
from app.schemas.search import SearchResponse
from app.services.event_service import EventService
from app.services.search_service import SearchService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["guest"])

EventServiceDep = Annotated[EventService, Depends(get_event_service)]
SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
StorageDep = Annotated[StorageService, Depends(get_storage_service)]

# Accepted selfie content types.
_ALLOWED_SELFIE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.get("/_debug/schema")
def debug_schema(session: SessionDep) -> dict:
    """TEMPORARY diagnostics: report events columns + any query error.

    Remove after debugging. Helps identify DB/model schema drift on deploys.
    """
    from sqlalchemy import inspect, text

    out: dict = {}
    try:
        insp = inspect(session.get_bind())
        out["events_columns"] = sorted(c["name"] for c in insp.get_columns("events"))
        out["photos_columns"] = sorted(c["name"] for c in insp.get_columns("photos"))
    except Exception as exc:  # noqa: BLE001
        out["inspect_error"] = f"{type(exc).__name__}: {exc}"
    try:
        session.exec(text("SELECT id, slug, drive_folder_id FROM events LIMIT 1"))
        out["select_drive_folder_id"] = "ok"
    except Exception as exc:  # noqa: BLE001
        out["select_drive_folder_id_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return out


@router.get("/e/{slug}", response_model=EventDetailOut)
def get_event(slug: str, service: EventServiceDep) -> EventDetailOut:
    """Return public event details, folders, and per-folder photo counts."""
    return service.get_event_detail_by_slug(slug)


@router.get("/e/{slug}/folders/{folder_id}/photos", response_model=list[PhotoOut])
def list_folder_photos(
    slug: str,
    folder_id: uuid.UUID,
    session: SessionDep,
    limit: int = 60,
    offset: int = 0,
) -> list[PhotoOut]:
    """List photos in a folder (paginated) for the gallery grid."""
    photos = PhotoRepository(session).list_for_folder(folder_id, limit, offset)
    return [PhotoOut.model_validate(p) for p in photos]


@router.post("/e/{slug}/search", response_model=SearchResponse)
async def search_by_selfie(
    slug: str,
    service: SearchServiceDep,
    selfie: Annotated[UploadFile, File(...)],
) -> SearchResponse:
    """Find photos matching a guest selfie.

    Privacy: the selfie is read into memory, used for a single vector search,
    and then discarded. It is never written to disk, Google Drive, or the database.
    """
    if selfie.content_type not in _ALLOWED_SELFIE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type.")
    selfie_bytes = await selfie.read()
    try:
        return service.search_by_selfie(slug, selfie_bytes)
    finally:
        # Explicitly drop the reference to the in-memory selfie bytes.
        del selfie_bytes


# Thumbnails are immutable per photo id; cache them for a year in the browser.
_THUMB_CACHE_CONTROL = "public, max-age=31536000, immutable"
_ORIGINAL_CACHE_CONTROL = "public, max-age=86400, immutable"


@router.get("/public/photos/{photo_id}/thumbnail")
def proxy_thumbnail(
    photo_id: uuid.UUID, session: SessionDep, storage: StorageDep
):
    """Serve the WebP thumbnail, preferring the local disk cache.

    Fast path: if a locally cached WebP exists, serve it directly via
    FileResponse. Fallback: regenerate the thumbnail from the Drive original,
    cache it, then serve it. This avoids Google Drive rendering/CORS issues.
    """
    thumbnails = ThumbnailService()

    # Fast path: serve the cached WebP straight from disk.
    if thumbnails.exists(photo_id):
        return FileResponse(
            thumbnails.path_for(photo_id),
            media_type="image/webp",
            headers={"Cache-Control": _THUMB_CACHE_CONTROL},
        )

    # Fallback: fetch the original from Drive, regenerate + cache the thumbnail.
    photo = PhotoRepository(session).get(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    original_bytes = storage.get_file_stream(photo.drive_original_id)
    thumbnails.generate(original_bytes, photo_id)
    return FileResponse(
        thumbnails.path_for(photo_id),
        media_type="image/webp",
        headers={"Cache-Control": _THUMB_CACHE_CONTROL},
    )


@router.get("/public/photos/{photo_id}/download")
def proxy_download(
    photo_id: uuid.UUID, session: SessionDep, storage: StorageDep
):
    """Stream the full-resolution original from Google Drive as an attachment."""
    photo = PhotoRepository(session).get(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    data = storage.get_file_stream(photo.drive_original_id)
    filename = f"{photo.id}.jpg"
    return StreamingResponse(
        iter([data]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": _ORIGINAL_CACHE_CONTROL,
        },
    )


# Backwards-compatible alias for the original download path.
@router.get("/photos/{photo_id}/download")
def download_photo(
    photo_id: uuid.UUID, session: SessionDep, storage: StorageDep
):
    """Alias of the public download proxy (kept for compatibility)."""
    return proxy_download(photo_id, session, storage)
