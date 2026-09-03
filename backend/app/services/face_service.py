"""Face detection and embedding extraction service.

Primary engine: InsightFace (buffalo_l, 512-d embeddings).
Fallback engine: face_recognition / dlib (128-d embeddings).

The engine is selected via settings.FACE_ENGINE. Models are loaded lazily and
cached at module level so the heavy initialization happens once per process.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.core.config import settings


@dataclass
class DetectedFace:
    """A detected face: a normalized embedding plus metadata."""

    embedding: list[float]
    bbox: dict  # {"x", "y", "w", "h"}
    det_score: float


class _InsightFaceEngine:
    """Lazy wrapper around InsightFace's FaceAnalysis app."""

    def __init__(self) -> None:
        from insightface.app import FaceAnalysis

        # buffalo_l provides detection + 512-d ArcFace recognition.
        self._app = FaceAnalysis(name="buffalo_l")
        # ctx_id=-1 forces CPU; det_size controls detector input resolution.
        self._app.prepare(ctx_id=-1, det_size=(640, 640))

    def extract(self, image: np.ndarray) -> list[DetectedFace]:
        faces = self._app.get(image)
        results: list[DetectedFace] = []
        for f in faces:
            # normed_embedding is L2-normalized, ideal for cosine similarity.
            emb = np.asarray(f.normed_embedding, dtype=np.float32)
            x1, y1, x2, y2 = [float(v) for v in f.bbox]
            results.append(
                DetectedFace(
                    embedding=emb.tolist(),
                    bbox={"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                    det_score=float(getattr(f, "det_score", 1.0)),
                )
            )
        return results


class _FaceRecognitionEngine:
    """Lazy wrapper around the face_recognition (dlib) library (128-d)."""

    def __init__(self) -> None:
        import face_recognition  # noqa: F401

        self._fr = face_recognition

    def extract(self, image: np.ndarray) -> list[DetectedFace]:
        locations = self._fr.face_locations(image)
        encodings = self._fr.face_encodings(image, locations)
        results: list[DetectedFace] = []
        for (top, right, bottom, left), enc in zip(locations, encodings):
            vec = np.asarray(enc, dtype=np.float32)
            # Normalize so cosine distance behaves consistently with InsightFace.
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(
                DetectedFace(
                    embedding=vec.tolist(),
                    bbox={
                        "x": float(left),
                        "y": float(top),
                        "w": float(right - left),
                        "h": float(bottom - top),
                    },
                    det_score=1.0,
                )
            )
        return results


class FaceService:
    """High-level face service used by the rest of the application."""

    _engine = None  # process-wide cached engine instance

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            if settings.FACE_ENGINE == "face_recognition":
                cls._engine = _FaceRecognitionEngine()
            else:
                cls._engine = _InsightFaceEngine()
        return cls._engine

    @staticmethod
    def _to_rgb_array(image_bytes: bytes) -> np.ndarray:
        """Decode image bytes into an RGB numpy array."""
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(img)

    def extract_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        """Detect and embed all faces in the given image bytes."""
        arr = self._to_rgb_array(image_bytes)
        return self._get_engine().extract(arr)

    def extract_primary_embedding(self, image_bytes: bytes) -> list[float] | None:
        """Return the embedding of the largest face (used for selfie search).

        The image bytes and the resulting embedding are ephemeral; callers must
        not persist them. Returns None when no face is detected.
        """
        faces = self.extract_faces(image_bytes)
        if not faces:
            return None
        # Pick the largest bounding box (closest / most prominent face).
        largest = max(faces, key=lambda f: f.bbox["w"] * f.bbox["h"])
        return largest.embedding
