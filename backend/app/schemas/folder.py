"""Folder schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FolderCreate(BaseModel):
    name: str = Field(min_length=1)
    position: int = 0


class FolderOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    position: int
    created_at: datetime
    photo_count: int = 0

    model_config = {"from_attributes": True}
