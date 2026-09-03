"""Upload job schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.upload_job import JobStatus


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
