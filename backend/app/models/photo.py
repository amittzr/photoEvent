"""Photo model."""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


class PhotoStatus(str, Enum):
    """Background-processing status for a photo."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Photo(SQLModel, table=True):
    """A single uploaded image with Google Drive references and status."""

    __tablename__ = "photos"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    folder_id: uuid.UUID = Field(foreign_key="folders.id", index=True, nullable=False)
    # event_id is denormalized to allow fast event-scoped queries and vector search.
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True, nullable=False)

    original_url: str = Field(nullable=False)
    thumb_url: str = Field(nullable=False)
    # Google Drive file ID for the full-resolution original.
    drive_original_id: str = Field(nullable=False)
    # Google Drive file ID for the thumbnail (optional; thumbnails are primarily
    # cached locally as WebP, so this may be null for newer uploads).
    drive_thumb_id: str | None = Field(default=None, nullable=True)

    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    status: PhotoStatus = Field(default=PhotoStatus.PENDING, nullable=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
