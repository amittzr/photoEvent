"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values are read from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg://photoevent:photoevent@localhost:5432/photoevent"
    )

    # --- Auth ---
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str | None = None
    ADMIN_PASSWORD_HASH: str | None = None

    # --- Google Drive storage ---
    # Auth mode: "oauth" (upload as a real user, uses their quota) or
    # "service_account" (no personal quota; requires a Shared Drive).
    DRIVE_AUTH_MODE: str = "oauth"
    # Path to the service-account JSON key (used when DRIVE_AUTH_MODE=service_account).
    GOOGLE_APPLICATION_CREDENTIALS: str = "/app/google-credentials.json"
    # OAuth client secrets JSON (Desktop app) downloaded from Google Cloud Console.
    GOOGLE_OAUTH_CLIENT_SECRETS: str = "/app/oauth-client-secrets.json"
    # Path where the generated OAuth token (with refresh token) is stored/read.
    GOOGLE_OAUTH_TOKEN_PATH: str = "/app/oauth-token.json"
    # Optional explicit overrides (e.g. Render Secret Files). When set, these
    # take precedence over both /etc/secrets and the local paths above.
    GOOGLE_CLIENT_SECRETS_FILE: str | None = None
    GOOGLE_TOKEN_FILE: str | None = None
    # Parent Drive folder under which all event folders/photos are created.
    GOOGLE_DRIVE_ROOT_FOLDER_ID: str = ""

    # --- Face recognition ---
    # face_recognition (dlib ResNet, 128-d, ~80MB RAM).
    # Replaces InsightFace (512-d, ~400MB) to fit Render's free 512MB tier.
    FACE_ENGINE: str = "face_recognition"
    FACE_EMBEDDING_DIM: int = 128
    FACE_MATCH_THRESHOLD: float = 0.45
    FACE_SEARCH_TOP_K: int = 200

    # --- App ---
    # Comma-separated list of allowed frontend origins for CORS.
    # e.g. "http://localhost:3000,https://photo-event-six.vercel.app"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    @property
    def frontend_origins(self) -> list[str]:
        """Parse FRONTEND_ORIGIN into a list of trimmed origins."""
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]

    # --- Thumbnails (local WebP cache) ---
    THUMBNAIL_DIR: str = "/app/data/thumbnails"
    THUMBNAIL_MAX_EDGE: int = 600
    THUMBNAIL_WEBP_QUALITY: int = 75

    # --- Bulk ZIP upload ---
    ZIP_TMP_DIR: str = "/tmp/photoevent"
    ZIP_MAX_WORKERS: int = 4


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
