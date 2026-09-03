"""Data-access layer for folders."""
import uuid

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.folder import Folder
from app.models.photo import Photo


class FolderRepository:
    """Encapsulates all DB operations for the Folder entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, folder: Folder) -> Folder:
        self.session.add(folder)
        self.session.commit()
        self.session.refresh(folder)
        return folder

    def get(self, folder_id: uuid.UUID) -> Folder | None:
        return self.session.get(Folder, folder_id)

    def list_for_event(self, event_id: uuid.UUID) -> list[Folder]:
        stmt = (
            select(Folder)
            .where(Folder.event_id == event_id)
            .order_by(Folder.position, Folder.created_at)
        )
        return list(self.session.exec(stmt))

    def photo_counts_for_event(self, event_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Return a mapping of folder_id -> photo count for an event."""
        stmt = (
            select(Photo.folder_id, func.count(Photo.id))
            .where(Photo.event_id == event_id)
            .group_by(Photo.folder_id)
        )
        return {folder_id: count for folder_id, count in self.session.exec(stmt)}

    def delete(self, folder: Folder) -> None:
        self.session.delete(folder)
        self.session.commit()
