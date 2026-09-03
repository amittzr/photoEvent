"""Google Drive storage manager service.

Supports two authentication modes (settings.DRIVE_AUTH_MODE):

- "oauth": authenticate as a real Google user via an OAuth refresh token.
  Uploaded files count against that user's personal Drive quota, so this works
  with consumer @gmail.com accounts. Generate the token once with
  scripts/generate_oauth_token.py.
- "service_account": authenticate with a service-account key. Service accounts
  have no personal storage quota, so this only works when the root folder lives
  in a Shared Drive.

All event folders and their photos live under a single parent folder identified
by GOOGLE_DRIVE_ROOT_FOLDER_ID. Uploaded files are granted public "reader"
permission for the "anyone" role so the web client can render them directly.

Google API errors are wrapped in StorageError so routers can return a clear
response (e.g. HTTP 502) instead of a raw 500.
"""
from __future__ import annotations

import io
import os
import threading

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from app.core.config import settings
from app.core.exceptions import StorageError

# Google Drive API scope required for creating folders and uploading files.
_SCOPES = ["https://www.googleapis.com/auth/drive"]

# MIME type Drive uses to represent a folder.
_FOLDER_MIME = "application/vnd.google-apps.folder"


def _build_credentials():
    """Build Drive API credentials based on the configured auth mode."""
    if settings.DRIVE_AUTH_MODE == "service_account":
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS, scopes=_SCOPES
        )

    # OAuth user-delegation mode: load the stored token (with refresh token).
    token_path = settings.GOOGLE_OAUTH_TOKEN_PATH
    if not os.path.exists(token_path):
        raise StorageError(
            "Google Drive OAuth token not found. Run "
            "scripts/generate_oauth_token.py to authorize a user account.",
            upstream_status=500,
        )
    creds = UserCredentials.from_authorized_user_file(token_path, _SCOPES)
    # Refresh the short-lived access token using the stored refresh token.
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise StorageError(
                "Google Drive OAuth token is invalid and cannot be refreshed. "
                "Re-run scripts/generate_oauth_token.py.",
                upstream_status=500,
            )
    return creds


class StorageService:
    """Google Drive-backed storage manager.

    The public method surface mirrors the previous GCS manager so callers only
    need minor changes: ``upload_bytes`` returns a Drive file ID (used where the
    code previously stored an object path), ``public_url`` returns a directly
    viewable link, and ``download_bytes`` streams the file back.
    """

    def __init__(self) -> None:
        credentials = _build_credentials()
        # cache_discovery=False avoids noisy warnings and filesystem cache writes.
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._root_folder_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        # Cache of "path" -> Drive folder ID to avoid repeated API lookups.
        self._folder_cache: dict[str, str] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Folder management
    # ------------------------------------------------------------------ #
    def create_subfolder(self, folder_name: str, parent_folder_id: str) -> str:
        """Create a folder under a parent, or return the existing one's ID.

        Lookups are scoped to the parent so folder names only need to be unique
        within their parent (matching filesystem-like semantics).
        """
        existing = self._find_child_folder(folder_name, parent_folder_id)
        if existing:
            return existing
        metadata = {
            "name": folder_name,
            "mimeType": _FOLDER_MIME,
            "parents": [parent_folder_id],
        }
        try:
            created = (
                self._service.files()
                .create(body=metadata, fields="id", supportsAllDrives=True)
                .execute()
            )
        except HttpError as exc:
            raise _wrap_http_error(exc, f"create folder '{folder_name}'") from exc
        return created["id"]

    def _find_child_folder(self, name: str, parent_folder_id: str) -> str | None:
        """Return the ID of a non-trashed child folder with the given name."""
        # Escape single quotes to keep the Drive query string valid.
        safe_name = name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and mimeType = '{_FOLDER_MIME}' "
            f"and '{parent_folder_id}' in parents and trashed = false"
        )
        try:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name)",
                    pageSize=1,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            raise _wrap_http_error(exc, f"look up folder '{name}'") from exc
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def _resolve_folder_path(self, path: str) -> str:
        """Resolve a slash-separated logical path to a Drive folder ID.

        Segments are created on demand under the configured root folder. Results
        are cached so repeated uploads to the same folder skip API round-trips.
        """
        with self._cache_lock:
            if path in self._folder_cache:
                return self._folder_cache[path]

            parent = self._root_folder_id
            accumulated = ""
            for segment in path.split("/"):
                if not segment:
                    continue
                accumulated = f"{accumulated}/{segment}" if accumulated else segment
                if accumulated in self._folder_cache:
                    parent = self._folder_cache[accumulated]
                    continue
                folder_id = self.create_subfolder(segment, parent)
                self._folder_cache[accumulated] = folder_id
                parent = folder_id
            return parent

    # ------------------------------------------------------------------ #
    # File upload / access
    # ------------------------------------------------------------------ #
    def upload_file(
        self,
        file_bytes: bytes,
        folder_id: str,
        file_name: str,
        mime_type: str,
    ) -> dict[str, str]:
        """Upload bytes into a Drive folder and grant public read access.

        Returns a dict with the Drive file ID plus view/thumbnail/download links.
        """
        metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), mimetype=mime_type, resumable=False
        )
        try:
            created = (
                self._service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id, webViewLink, webContentLink, thumbnailLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            raise _wrap_http_error(exc, f"upload '{file_name}'") from exc

        file_id = created["id"]
        self._grant_public_read(file_id)
        return {
            "id": file_id,
            "web_view_link": created.get("webViewLink", ""),
            "web_content_link": created.get("webContentLink", ""),
            "thumbnail_link": created.get("thumbnailLink", ""),
        }

    def upload_bytes(self, data: bytes, object_path: str, content_type: str) -> str:
        """Upload bytes to a logical path and return the Drive file ID.

        ``object_path`` is a slash-separated path like
        "events/{id}/originals/{photo}.jpg". The directory portion is resolved to
        a Drive folder (created if needed) and the last segment becomes the file
        name. This keeps existing callers working with minimal changes.
        """
        folder_path, _, file_name = object_path.rpartition("/")
        folder_id = (
            self._resolve_folder_path(folder_path)
            if folder_path
            else self._root_folder_id
        )
        result = self.upload_file(data, folder_id, file_name, content_type)
        return result["id"]

    def _grant_public_read(self, file_id: str) -> None:
        """Grant the 'anyone' role reader permission on a file."""
        try:
            self._service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise _wrap_http_error(exc, "set public permission") from exc

    def get_public_url(self, file_id: str) -> str:
        """Return a directly viewable URL for a public Drive file.

        This URL form serves the file bytes inline (works well for <img> tags),
        unlike the standard webViewLink which opens the Drive UI.
        """
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    # Backwards-compatible alias used by existing callers.
    def public_url(self, file_id: str) -> str:
        """Alias for get_public_url (kept for caller compatibility)."""
        return self.get_public_url(file_id)

    def get_file_stream(self, file_id: str) -> bytes:
        """Download a Drive file's bytes."""
        request = self._service.files().get_media(
            fileId=file_id, supportsAllDrives=True
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        try:
            done = False
            while not done:
                _, done = downloader.next_chunk()
        except HttpError as exc:
            raise _wrap_http_error(exc, "download file") from exc
        return buffer.getvalue()

    # Backwards-compatible alias used by existing callers.
    def download_bytes(self, file_id: str) -> bytes:
        """Alias for get_file_stream (kept for caller compatibility)."""
        return self.get_file_stream(file_id)


def _wrap_http_error(exc: HttpError, action: str) -> StorageError:
    """Translate a googleapiclient HttpError into a readable StorageError."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    # exc.reason holds Google's human-readable message when available.
    reason = getattr(exc, "reason", None) or str(exc)
    return StorageError(
        f"Google Drive failed to {action}: {reason}",
        upstream_status=int(status) if status else None,
    )
