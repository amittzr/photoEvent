"""Upload job schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.upload_job import JobStatus


class DriveSyncRequest(BaseModel):
    """Optional overrides for a Drive folder sync.

    If drive_folder_id is omitted, the event's stored drive_folder_id is used.
    """

    drive_folder_id: str | None = None
    target_folder_id: uuid.UUID | None = None


class UploadJobOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    folder_id: uuid.UUID
    status: JobStatus
    total: int
    processed: int
    failed: int
    message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
