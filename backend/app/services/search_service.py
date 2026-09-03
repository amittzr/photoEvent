"""Selfie search service: privacy-preserving vector similarity search."""
import uuid

from fastapi import HTTPException

from app.core.config import settings
from app.repositories.event_repository import EventRepository
from app.repositories.face_repository import FaceRepository
from app.repositories.photo_repository import PhotoRepository
from app.schemas.photo import PhotoOut
from app.schemas.search import PhotoMatchOut, SearchResponse
from app.services.face_service import FaceService


class SearchService:
    """Runs a selfie against an event's face embeddings.

    Privacy: the selfie bytes and its embedding exist only for the duration of
    this call. Nothing is written to disk, Google Drive, or the database.
    """

    def __init__(
        self,
        event_repo: EventRepository,
        face_repo: FaceRepository,
        photo_repo: PhotoRepository,
        face_service: FaceService,
    ) -> None:
        self.event_repo = event_repo
        self.face_repo = face_repo
        self.photo_repo = photo_repo
        self.face_service = face_service

    def search_by_selfie(self, slug: str, selfie_bytes: bytes) -> SearchResponse:
        event = self.event_repo.get_by_slug(slug)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found.")

        faces = self.face_service.extract_faces(selfie_bytes)
        if not faces:
            return SearchResponse(matches=[], faces_detected_in_selfie=0)

        # Use the largest detected face as the query.
        query = max(faces, key=lambda f: f.bbox["w"] * f.bbox["h"]).embedding

        results = self.face_repo.search(
            event_id=event.id,
            embedding=query,
            top_k=settings.FACE_SEARCH_TOP_K,
            max_distance=settings.FACE_MATCH_THRESHOLD,
        )

        # Keep the best (smallest) distance per photo.
        best_by_photo: dict[uuid.UUID, float] = {}
        for photo_id, distance in results:
            if photo_id not in best_by_photo or distance < best_by_photo[photo_id]:
                best_by_photo[photo_id] = distance

        photos = {p.id: p for p in self.photo_repo.get_many(list(best_by_photo))}

        matches = [
            PhotoMatchOut(
                photo=PhotoOut.model_validate(photos[pid]),
                # Convert cosine distance to a 0..1 similarity for display.
                similarity=round(1.0 - dist, 4),
            )
            for pid, dist in best_by_photo.items()
            if pid in photos
        ]
        matches.sort(key=lambda m: m.similarity, reverse=True)

        # selfie_bytes and query go out of scope here; nothing persisted.
        return SearchResponse(
            matches=matches, faces_detected_in_selfie=len(faces)
        )
