"""Upload job model for tracking background ZIP processing."""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    """Lifecycle status of a bulk upload job."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class UploadJob(SQLModel, table=True):
    """Tracks the progress of an asynchronous ZIP bulk-upload."""

    __tablename__ = "upload_jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True, nullable=False)
    folder_id: uuid.UUID = Field(foreign_key="folders.id", nullable=False)

    status: JobStatus = Field(default=JobStatus.PENDING, nullable=False)
    total: int = Field(default=0, nullable=False)
    processed: int = Field(default=0, nullable=False)
    failed: int = Field(default=0, nullable=False)
    message: str | None = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
