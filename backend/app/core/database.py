"""Database engine and session management."""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from app.core.config import settings

# echo=False keeps logs clean; pool_pre_ping avoids stale connections.
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Create any missing tables without dropping existing data.

    Importing app.models registers every SQLModel table on SQLModel.metadata.
    We enable the pgvector extension first because the ``faces`` table has a
    ``vector`` column, and ``create_all`` would fail if the extension is absent
    (e.g. on a fresh Neon PostgreSQL database). ``create_all`` is idempotent:
    it only creates tables that don't already exist and never drops data.
    """
    # Import here (not at module top) to avoid import cycles and to ensure all
    # models are registered on the metadata before create_all runs.
    import app.models  # noqa: F401

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # create_all only creates MISSING tables; it never alters existing ones.
    SQLModel.metadata.create_all(engine)

    # Lightweight, idempotent column backfills for tables that predate a column.
    # This keeps deployments where migrations didn't run (e.g. Neon) self-healing
    # without dropping data. Each statement is a no-op if the column exists.
    _ensure_columns()


def _ensure_columns() -> None:
    """Add columns that may be missing on pre-existing tables (idempotent)."""
    statements = [
        # events.drive_folder_id (added for linking an existing Drive folder).
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR",
        # photos.drive_thumb_id became nullable; ensure the column exists.
        "ALTER TABLE photos ADD COLUMN IF NOT EXISTS drive_thumb_id VARCHAR",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
