"""Local WebP thumbnail generation and caching."""
from __future__ import annotations

import io
import os
import uuid

from PIL import Image, ImageOps

from app.core.config import settings


class ThumbnailService:
    """Generates and locates WebP thumbnails on local disk.

    All disk operations are best-effort — if the directory isn't writable
    (e.g. no persistent disk on Render free tier) thumbnails are silently
    skipped. The proxy endpoint regenerates them from Drive on demand.
    """

    def __init__(self) -> None:
        self._dir = settings.THUMBNAIL_DIR
        try:
            os.makedirs(self._dir, exist_ok=True)
        except OSError:
            pass

    def path_for(self, photo_id: uuid.UUID) -> str:
        return os.path.join(self._dir, f"{photo_id}.webp")

    def exists(self, photo_id: uuid.UUID) -> bool:
        return os.path.isfile(self.path_for(photo_id))

    def delete(self, photo_id: uuid.UUID) -> None:
        try:
            os.remove(self.path_for(photo_id))
        except OSError:
            pass

    def generate(self, image_bytes: bytes, photo_id: uuid.UUID) -> tuple[int, int]:
        """Generate WebP thumbnail and try to cache it on disk.

        Returns (original_width, original_height). Disk write is best-effort:
        if it fails the photo row is still created and the thumbnail will be
        regenerated from Drive on the first request.
        """
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        orig_w, orig_h = img.size

        thumb = img.convert("RGB")
        thumb.thumbnail(
            (settings.THUMBNAIL_MAX_EDGE, settings.THUMBNAIL_MAX_EDGE),
            Image.LANCZOS,
        )

        try:
            os.makedirs(self._dir, exist_ok=True)
            final_path = self.path_for(photo_id)
            tmp_path = f"{final_path}.tmp"
            thumb.save(tmp_path, format="WEBP",
                       quality=settings.THUMBNAIL_WEBP_QUALITY, method=6)
            os.replace(tmp_path, final_path)
        except OSError:
            pass  # No persistent disk — fallback via Drive proxy is fine.

        return orig_w, orig_h
