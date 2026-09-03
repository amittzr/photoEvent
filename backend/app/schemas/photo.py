"""Photo schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field

from app.models.photo import PhotoStatus


class PhotoOut(BaseModel):
    """Public photo DTO.

    Image URLs point at the backend proxy endpoints (not raw Drive links), so
    the browser can render them reliably without Google Drive CORS/rendering
    quirks. The URLs are derived from the photo id at serialization time.
    """

    id: uuid.UUID
    folder_id: uuid.UUID
    event_id: uuid.UUID
    width: int | None
    height: int | None
    status: PhotoStatus
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def thumb_url(self) -> str:
        """Relative proxy URL for the optimized thumbnail."""
        return f"/api/public/photos/{self.id}/thumbnail"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def original_url(self) -> str:
        """Relative proxy URL for the full-resolution original (attachment)."""
        return f"/api/public/photos/{self.id}/download"


class UploadResult(BaseModel):
    uploaded: list[PhotoOut]
