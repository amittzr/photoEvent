"""Authentication service for the single admin account."""
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)


class AuthService:
    """Validates admin credentials and issues JWT tokens.

    The admin credential is derived from environment variables:
    - ADMIN_PASSWORD_HASH takes precedence if set.
    - Otherwise ADMIN_PASSWORD is hashed once at startup.
    """

    def __init__(self) -> None:
        self._username = settings.ADMIN_USERNAME
        if settings.ADMIN_PASSWORD_HASH:
            self._password_hash = settings.ADMIN_PASSWORD_HASH
        elif settings.ADMIN_PASSWORD:
            self._password_hash = hash_password(settings.ADMIN_PASSWORD)
        else:
            self._password_hash = None

    def authenticate(self, username: str, password: str) -> str | None:
        """Return a JWT access token when credentials are valid, else None."""
        if self._password_hash is None:
            return None
        if username != self._username:
            return None
        if not verify_password(password, self._password_hash):
            return None
        return create_access_token(subject=username)
