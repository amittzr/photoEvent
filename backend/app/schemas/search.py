"""Selfie-search schemas."""
from pydantic import BaseModel

from app.schemas.photo import PhotoOut


class PhotoMatchOut(BaseModel):
    """A matched photo with its best similarity score (0..1, higher = closer)."""

    photo: PhotoOut
    similarity: float


class SearchResponse(BaseModel):
    matches: list[PhotoMatchOut]
    faces_detected_in_selfie: int
