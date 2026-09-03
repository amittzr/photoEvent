"""Folder (category) model."""
import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Folder(SQLModel, table=True):
    """A category/sub-folder within an event (e.g., "חתונה")."""

    __tablename__ = "folders"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True, nullable=False)
    name: str = Field(nullable=False)
    position: int = Field(default=0, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
