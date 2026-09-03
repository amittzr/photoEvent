"""Data-access layer for photos."""
import uuid

from sqlmodel import Session, select

from app.models.photo import Photo, PhotoStatus


class PhotoRepository:
    """Encapsulates all DB operations for the Photo entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, photo: Photo) -> Photo:
        self.session.add(photo)
        self.session.commit()
        self.session.refresh(photo)
        return photo

    def get(self, photo_id: uuid.UUID) -> Photo | None:
        return self.session.get(Photo, photo_id)

    def list_for_folder(
        self, folder_id: uuid.UUID, limit: int = 60, offset: int = 0
    ) -> list[Photo]:
        stmt = (
            select(Photo)
            .where(Photo.folder_id == folder_id)
            .order_by(Photo.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.exec(stmt))

    def get_many(self, photo_ids: list[uuid.UUID]) -> list[Photo]:
        if not photo_ids:
            return []
        stmt = select(Photo).where(Photo.id.in_(photo_ids))
        return list(self.session.exec(stmt))

    def all_for_folder(self, folder_id: uuid.UUID) -> list[Photo]:
        """Return every photo in a folder (unpaginated), for cleanup tasks."""
        stmt = select(Photo).where(Photo.folder_id == folder_id)
        return list(self.session.exec(stmt))

    def existing_drive_ids_for_event(self, event_id: uuid.UUID) -> set[str]:
        """Return Drive file IDs already imported for this event (for dedup)."""
        stmt = select(Photo.drive_original_id).where(Photo.event_id == event_id)
        return {row for row in self.session.exec(stmt) if row}

    def set_status(self, photo_id: uuid.UUID, status: PhotoStatus) -> None:
        photo = self.session.get(Photo, photo_id)
        if photo:
            photo.status = status
            self.session.add(photo)
            self.session.commit()
