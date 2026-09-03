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

    SQLModel.metadata.create_all(engine)
