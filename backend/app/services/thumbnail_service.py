"""Local WebP thumbnail generation and caching.

Thumbnails are generated as WebP (small, fast) and stored on a local disk
volume keyed by photo id, so they can be served instantly via FileResponse.
Originals continue to live on Google Drive.
"""
from __future__ import annotations

import io
import os
import uuid

from PIL import Image, ImageOps

from app.core.config import settings


class ThumbnailService:
    """Generates and locates WebP thumbnails on local disk."""

    def __init__(self) -> None:
        self._dir = settings.THUMBNAIL_DIR
        try:
            os.makedirs(self._dir, exist_ok=True)
        except OSError:
            # Directory creation may fail on environments without a mounted disk
            # (e.g. Render free tier without a persistent disk). Thumbnails will
            # be regenerated from Drive on every request in that case.
            pass

    def path_for(self, photo_id: uuid.UUID) -> str:
        """Return the local filesystem path for a photo's WebP thumbnail."""
        return os.path.join(self._dir, f"{photo_id}.webp")

    def exists(self, photo_id: uuid.UUID) -> bool:
        """True if a cached thumbnail file already exists on disk."""
        return os.path.isfile(self.path_for(photo_id))

    def delete(self, photo_id: uuid.UUID) -> None:
        """Remove a cached thumbnail file if present (no error if missing)."""
        try:
            os.remove(self.path_for(photo_id))
        except OSError:
            pass

    def generate(self, image_bytes: bytes, photo_id: uuid.UUID) -> tuple[int, int]:
        """Create a WebP thumbnail from image bytes and write it to disk.

        Returns the ORIGINAL image (width, height). If the disk is unavailable
        (e.g. no persistent disk on Render), the dimensions are still returned
        so the caller can persist the photo row — the thumbnail will be
        regenerated from Drive on the first request that needs it.
        """
        img = Image.open(io.BytesIO(image_bytes))
        # Respect EXIF orientation so thumbnails aren't rotated.
        img = ImageOps.exif_transpose(img)
        orig_w, orig_h = img.size

        thumb = img.convert("RGB")
        thumb.thumbnail(
            (settings.THUMBNAIL_MAX_EDGE, settings.THUMBNAIL_MAX_EDGE),
            Image.LANCZOS,
        )

        # Best-effort: try to write the thumbnail to disk. If the directory
        # doesn't exist or isn't writable, skip — the proxy endpoint has a
        # Drive fallback that regenerates the thumbnail on the fly.
        try:
            os.makedirs(self._dir, exist_ok=True)
            final_path = self.path_for(photo_id)
            tmp_path = f"{final_path}.tmp"
            thumb.save(
                tmp_path,
                format="WEBP",
                quality=settings.THUMBNAIL_WEBP_QUALITY,
                method=6,
            )
            os.replace(tmp_path, final_path)
        except OSError:
            pass

        return orig_w, orig_h
