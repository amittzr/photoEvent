"""Helpers to build human-readable, collision-safe Google Drive folder paths.

Drive folders are organized as:

    {root}/{event_title (id8)}/{category_name}/{photo_id}.{ext}

Event titles can repeat, so a short 8-char slice of the event UUID is appended
to keep the top-level event folder unique and stable. Category (sub-folder)
names are used as-is (sanitized) so the layout is easy to browse in Drive.
"""
from __future__ import annotations

import re
import uuid

# Characters that are awkward or illegal in folder names across systems.
_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _sanitize(name: str, fallback: str) -> str:
    """Make a string safe to use as a Drive folder name."""
    cleaned = _UNSAFE.sub(" ", (name or "")).strip()
    # Collapse repeated whitespace and trim length for tidy folder names.
    cleaned = re.sub(r"\s+", " ", cleaned)[:80].strip()
    return cleaned or fallback


def event_folder_name(event_id: uuid.UUID, title: str) -> str:
    """Readable, unique folder name for an event, e.g. 'Wedding David & Sarah (eaa15f25)'."""
    short_id = str(event_id).split("-")[0]
    safe_title = _sanitize(title, fallback="event")
    return f"{safe_title} ({short_id})"


def category_folder_name(folder_name: str) -> str:
    """Readable folder name for a category/sub-folder."""
    return _sanitize(folder_name, fallback="Photos")


def build_object_path(
    event_id: uuid.UUID,
    event_title: str,
    folder_name: str,
    photo_id: uuid.UUID,
    ext: str,
) -> str:
    """Build the full logical Drive path for an original photo."""
    ext = ext if ext.startswith(".") else f".{ext}"
    return (
        f"{event_folder_name(event_id, event_title)}/"
        f"{category_folder_name(folder_name)}/"
        f"{photo_id}{ext}"
    )
