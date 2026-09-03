"""Face detection and 128-d embedding extraction using face_recognition (dlib).

face_recognition wraps dlib's ResNet face descriptor model which produces
128-dimensional L2-normalised embeddings. RAM usage ~80MB — fits on Render's
free 512MB tier (vs InsightFace buffalo_l at ~400MB).
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


class DetectedFace:
    """A detected face: a normalised 128-d embedding plus bounding-box metadata."""

    def __init__(self, embedding: list[float], bbox: dict, det_score: float) -> None:
        self.embedding = embedding
        self.bbox = bbox
        self.det_score = det_score


def _load_fr():
    """Lazy import of face_recognition so dlib model loads only when first needed."""
    import face_recognition as fr  # noqa: PLC0415
    return fr


def _to_rgb_array(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def _normalise(vec: np.ndarray) -> list[float]:
    """L2-normalise for consistent cosine similarity with pgvector."""
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


class FaceService:
    """128-d face embedding service backed by face_recognition (dlib).

    The dlib model is loaded lazily so heavy initialisation happens once per
    worker process and does not affect startup time.
    """

    _fr = None  # process-wide cached module reference

    @classmethod
    def _get_fr(cls):
        if cls._fr is None:
            cls._fr = _load_fr()
        return cls._fr

    def extract_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        """Detect all faces and return their 128-d embeddings."""
        arr = _to_rgb_array(image_bytes)
        fr = self._get_fr()
        locations = fr.face_locations(arr)
        if not locations:
            return []
        encodings = fr.face_encodings(arr, locations)
        results: list[DetectedFace] = []
        for (top, right, bottom, left), enc in zip(locations, encodings):
            results.append(DetectedFace(
                embedding=_normalise(np.asarray(enc, dtype=np.float32)),
                bbox={"x": float(left), "y": float(top),
                      "w": float(right - left), "h": float(bottom - top)},
                det_score=1.0,
            ))
        return results

    def extract_primary_embedding(self, image_bytes: bytes) -> list[float] | None:
        """Return the embedding of the largest face (used for selfie search)."""
        faces = self.extract_faces(image_bytes)
        if not faces:
            return None
        return max(faces, key=lambda f: f.bbox["w"] * f.bbox["h"]).embedding
