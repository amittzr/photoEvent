"""Application-level exceptions."""


class StorageError(Exception):
    """Raised when the storage backend (Google Drive) fails.

    Carries a human-readable message plus the upstream HTTP status so routers
    can translate it into a clear API response instead of a raw 500.
    """

    def __init__(self, message: str, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.upstream_status = upstream_status
