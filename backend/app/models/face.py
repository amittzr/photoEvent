"""Face model holding a pgvector embedding per detected face."""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.config import settings


class Face(SQLModel, table=True):
    """A single detected face and its embedding, linked to a photo."""

    __tablename__ = "faces"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    photo_id: uuid.UUID = Field(foreign_key="photos.id", index=True, nullable=False)
    # Denormalized event_id so vector search can be scoped without a join.
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True, nullable=False)

    # pgvector column; 128-d (dlib face_recognition).
    embedding: list[float] = Field(
        sa_column=Column(Vector(settings.FACE_EMBEDDING_DIM), nullable=False)
    )

    # Bounding box {"x","y","w","h"} of the detected face.
    bbox: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    det_score: float | None = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
