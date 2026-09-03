"""Upload orchestration: thumbnails, Google Drive upload, and async face indexing."""
from __future__ import annotations

import uuid

from app.core.database import engine
from app.models.face import Face
from app.models.photo import Photo, PhotoStatus
from app.repositories.face_repository import FaceRepository
from app.repositories.photo_repository import PhotoRepository
from app.services.drive_paths import build_object_path
from app.services.face_service import FaceService
from app.services.storage_service import StorageService
from app.services.thumbnail_service import ThumbnailService
from sqlmodel import Session


class UploadService:
    """Handles the full lifecycle of an uploaded photo."""

    def __init__(
        self,
        photo_repo: PhotoRepository,
        storage: StorageService,
    ) -> None:
        self.photo_repo = photo_repo
        self.storage = storage
        self.thumbnails = ThumbnailService()

    def upload_photo(
        self,
        event_id: uuid.UUID,
        folder_id: uuid.UUID,
        image_bytes: bytes,
        content_type: str,
        original_ext: str,
        event_title: str,
        folder_name: str,
    ) -> Photo:
        """Cache a local WebP thumbnail, upload the original to Drive, persist.

        The thumbnail is generated locally (WebP, ~600px) for instant serving;
        only the high-resolution original is uploaded to Google Drive, under a
        human-readable "{event title (id)}/{category}" folder path.
        """
        photo_id = uuid.uuid4()

        # Generate + cache the WebP thumbnail on local disk.
        width, height = self.thumbnails.generate(image_bytes, photo_id)

        # Upload only the original to Drive; upload_bytes returns the file ID.
        original_path = build_object_path(
            event_id, event_title, folder_name, photo_id, original_ext
        )
        original_id = self.storage.upload_bytes(
            image_bytes, original_path, content_type
        )

        photo = Photo(
            id=photo_id,
            folder_id=folder_id,
            event_id=event_id,
            drive_original_id=original_id,
            drive_thumb_id=None,
            original_url=self.storage.get_public_url(original_id),
            thumb_url=f"/api/public/photos/{photo_id}/thumbnail",
            width=width,
            height=height,
            status=PhotoStatus.PENDING,
        )
        return self.photo_repo.create(photo)

    @staticmethod
    def index_faces_task(
        photo_id: uuid.UUID, event_id: uuid.UUID, drive_original_id: str
    ) -> None:
        """Background task: extract face embeddings and store them.

        Runs with its own DB session because it executes outside the request
        lifecycle. Downloads the original from Google Drive, extracts faces,
        persists Face rows, and updates the photo status.
        """
        with Session(engine) as session:
            photo_repo = PhotoRepository(session)
            face_repo = FaceRepository(session)
            photo_repo.set_status(photo_id, PhotoStatus.PROCESSING)
            try:
                storage = StorageService()
                image_bytes = storage.get_file_stream(drive_original_id)
                detected = FaceService().extract_faces(image_bytes)
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
                face_repo.bulk_create(faces)
                photo_repo.set_status(photo_id, PhotoStatus.DONE)
            except Exception:
                # Mark as failed so it can be retried/inspected; do not crash worker.
                photo_repo.set_status(photo_id, PhotoStatus.FAILED)
                raise
