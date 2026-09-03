"""Data-access layer for faces, including pgvector similarity search."""
import uuid

from sqlmodel import Session, select

from app.models.face import Face


class FaceRepository:
    """Encapsulates DB operations for the Face entity and vector search."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_create(self, faces: list[Face]) -> None:
        if not faces:
            return
        self.session.add_all(faces)
        self.session.commit()

    def search(
        self,
        event_id: uuid.UUID,
        embedding: list[float],
        top_k: int,
        max_distance: float,
    ) -> list[tuple[uuid.UUID, float]]:
        """Cosine-distance ANN search scoped to an event.

        Returns a list of (photo_id, distance) tuples ordered by ascending
        distance (closest first). Uses pgvector's ``<=>`` cosine operator.
        """
        distance = Face.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(Face.photo_id, distance)
            .where(Face.event_id == event_id)
            .where(distance <= max_distance)
            .order_by(distance)
            .limit(top_k)
        )
        return [(row[0], float(row[1])) for row in self.session.exec(stmt)]
