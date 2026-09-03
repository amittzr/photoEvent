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


# Records the last init_db error so /health can surface schema/init problems
# instead of failing silently. None means the last init succeeded.
LAST_INIT_ERROR: str | None = None


def _ensure_columns() -> None:
    """Add columns that may be missing on pre-existing tables (idempotent).

    Also ensures foreign keys have ON DELETE CASCADE so folder/photo deletes
    work correctly. Each statement runs in its own transaction.
    """
    column_stmts = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR",
        "ALTER TABLE folders ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE photos ADD COLUMN IF NOT EXISTS drive_thumb_id VARCHAR",
        "ALTER TABLE photos ADD COLUMN IF NOT EXISTS drive_original_id VARCHAR",
        "ALTER TABLE photos ADD COLUMN IF NOT EXISTS thumb_url VARCHAR",
        "ALTER TABLE photos ADD COLUMN IF NOT EXISTS original_url VARCHAR",
    ]
    for stmt in column_stmts:
        with engine.begin() as conn:
            conn.execute(text(stmt))

    # Ensure foreign keys have ON DELETE CASCADE. We drop and re-add them only
    # if the current constraint lacks cascade (safe to run multiple times).
    fk_stmts = [
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'photos_folder_id_fkey'
          ) THEN
            ALTER TABLE photos DROP CONSTRAINT photos_folder_id_fkey;
          END IF;
          ALTER TABLE photos ADD CONSTRAINT photos_folder_id_fkey
            FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE;
        END $$;
        """,
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'faces_photo_id_fkey'
          ) THEN
            ALTER TABLE faces DROP CONSTRAINT faces_photo_id_fkey;
          END IF;
          ALTER TABLE faces ADD CONSTRAINT faces_photo_id_fkey
            FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE;
        END $$;
        """,
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'upload_jobs_folder_id_fkey'
          ) THEN
            ALTER TABLE upload_jobs DROP CONSTRAINT upload_jobs_folder_id_fkey;
          END IF;
          ALTER TABLE upload_jobs ADD CONSTRAINT upload_jobs_folder_id_fkey
            FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE;
        END $$;
        """,
    ]
    for stmt in fk_stmts:
        with engine.begin() as conn:
            conn.execute(text(stmt))
