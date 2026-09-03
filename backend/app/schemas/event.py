"""Event schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.folder import FolderOut


class EventCreate(BaseModel):
    title: str = Field(min_length=1)
    slug: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    event_date: date | None = None
    # Optional Google Drive folder ID to ingest existing photos from.
    drive_folder_id: str | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    event_date: date | None = None
    drive_folder_id: str | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    event_date: date | None
    drive_folder_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventDetailOut(EventOut):
    """Public event detail including its folders and per-folder photo counts."""

    folders: list[FolderOut]
