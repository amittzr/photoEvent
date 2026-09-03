"""Business logic for events and folders."""
import uuid

from fastapi import HTTPException, status

from app.models.event import Event
from app.models.folder import Folder
from app.repositories.event_repository import EventRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.photo_repository import PhotoRepository
from app.schemas.event import (
    EventCreate,
    EventDetailOut,
    EventOut,
    EventUpdate,
)
from app.schemas.folder import FolderCreate, FolderOut, FolderUpdate
from app.services.thumbnail_service import ThumbnailService


class EventService:
    """Coordinates event and folder use-cases via repositories."""

    def __init__(
        self,
        event_repo: EventRepository,
        folder_repo: FolderRepository,
        photo_repo: PhotoRepository,
    ) -> None:
        self.event_repo = event_repo
        self.folder_repo = folder_repo
        self.photo_repo = photo_repo

    # --- Events ---
    def create_event(self, data: EventCreate) -> EventOut:
        if self.event_repo.get_by_slug(data.slug):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An event with this slug already exists.",
            )
        event = Event(
            title=data.title,
            slug=data.slug,
            event_date=data.event_date,
            drive_folder_id=data.drive_folder_id,
        )
        return EventOut.model_validate(self.event_repo.create(event))

    def list_events(self) -> list[EventOut]:
        return [EventOut.model_validate(e) for e in self.event_repo.list_all()]

    def _get_or_404(self, event_id: uuid.UUID) -> Event:
        event = self.event_repo.get(event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found.")
        return event

    def update_event(self, event_id: uuid.UUID, data: EventUpdate) -> EventOut:
        event = self._get_or_404(event_id)
        if data.slug and data.slug != event.slug:
            existing = self.event_repo.get_by_slug(data.slug)
            if existing and existing.id != event.id:
                raise HTTPException(status_code=409, detail="Slug already in use.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(event, field, value)
        return EventOut.model_validate(self.event_repo.update(event))

    def delete_event(self, event_id: uuid.UUID) -> None:
        event = self._get_or_404(event_id)
        self.event_repo.delete(event)

    # --- Guest view ---
    def get_event_detail_by_slug(self, slug: str) -> EventDetailOut:
        event = self.event_repo.get_by_slug(slug)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found.")
        counts = self.folder_repo.photo_counts_for_event(event.id)
        folders = [
            FolderOut(
                id=f.id,
                event_id=f.event_id,
                name=f.name,
                position=f.position,
                created_at=f.created_at,
                photo_count=counts.get(f.id, 0),
            )
            for f in self.folder_repo.list_for_event(event.id)
        ]
        return EventDetailOut(
            id=event.id,
            title=event.title,
            slug=event.slug,
            event_date=event.event_date,
            drive_folder_id=event.drive_folder_id,
            created_at=event.created_at,
            folders=folders,
        )

    # --- Folders ---
    def create_folder(self, event_id: uuid.UUID, data: FolderCreate) -> FolderOut:
        self._get_or_404(event_id)
        folder = Folder(event_id=event_id, name=data.name, position=data.position)
        return FolderOut.model_validate(self.folder_repo.create(folder))

    def rename_folder(self, folder_id: uuid.UUID, data: FolderUpdate) -> FolderOut:
        folder = self.folder_repo.get(folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found.")
        folder.name = data.name
        updated = self.folder_repo.create(folder)  # add+commit+refresh (upsert)
        counts = self.folder_repo.photo_counts_for_event(updated.event_id)
        return FolderOut(
            id=updated.id,
            event_id=updated.event_id,
            name=updated.name,
            position=updated.position,
            created_at=updated.created_at,
            photo_count=counts.get(updated.id, 0),
        )

    def delete_folder(self, folder_id: uuid.UUID, cascade: bool = True) -> None:
        """Delete a folder.

        When cascade is True (default), also remove each photo's local WebP
        thumbnail and its Google Drive original before deleting DB rows. The DB
        cascade (ondelete=CASCADE) removes photo + face rows once the folder is
        deleted, but external artifacts (disk, Drive) must be cleaned explicitly.
        """
        folder = self.folder_repo.get(folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found.")

        if cascade:
            # Best-effort cleanup of external artifacts — NEVER block the DB delete.
            try:
                thumbnails = ThumbnailService()
                storage = None
                photos = self.photo_repo.all_for_folder(folder_id)
                for photo in photos:
                    # Remove the local WebP thumbnail cache.
                    try:
                        thumbnails.delete(photo.id)
                    except Exception:
                        pass
                    # Remove the Drive original.
                    if photo.drive_original_id:
                        try:
                            if storage is None:
                                from app.services.storage_service import StorageService

                                storage = StorageService()
                            storage.delete_file(photo.drive_original_id)
                        except Exception:
                            pass
            except Exception:
                # If cleanup fails entirely (e.g. no disk, no Drive creds),
                # log and continue — the DB delete must still happen.
                import logging

                logging.getLogger(__name__).warning(
                    "Cascade cleanup failed for folder %s; proceeding with DB delete.",
                    folder_id,
                    exc_info=True,
                )

        # Deleting the folder cascades to photos + faces at the DB level.
        self.folder_repo.delete(folder)
