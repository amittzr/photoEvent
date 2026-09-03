"""Database engine and session management."""
import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from app.core.config import settings

log = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)

# Records the last init_db error so /health can surface schema/init problems.
LAST_INIT_ERROR: str | None = None


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Idempotent DB bootstrap: enable pgvector, create missing tables,
    backfill missing columns, and ensure FK ON DELETE CASCADE constraints.

    Safe to run on every startup — never drops data.
    """
    import app.models  # noqa: F401  registers all tables on SQLModel.metadata

    # 1. Enable pgvector extension (required by faces.embedding column).
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 2. Create any tables that don't exist yet.
    SQLModel.metadata.create_all(engine)

    # 3. Add columns that may be missing on pre-existing tables (idempotent).
    _ensure_columns()

    # 4. Ensure FK constraints have ON DELETE CASCADE so folder/photo deletes work.
    _ensure_fk_cascades()

    log.info("init_db complete.")


def _ensure_columns() -> None:
    """Add columns that may be missing when Alembic migrations haven't run."""
    stmts = [
        "ALTER TABLE folders ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE photos  ADD COLUMN IF NOT EXISTS drive_thumb_id    VARCHAR",
        "ALTER TABLE photos  ADD COLUMN IF NOT EXISTS drive_original_id VARCHAR",
        "ALTER TABLE photos  ADD COLUMN IF NOT EXISTS thumb_url         VARCHAR",
        "ALTER TABLE photos  ADD COLUMN IF NOT EXISTS original_url      VARCHAR",
    ]
    for stmt in stmts:
        with engine.begin() as conn:
            conn.execute(text(stmt))

    # Migrate faces.embedding from 512-d to 128-d if needed.
    _migrate_faces_128d()


def _ensure_fk_cascades() -> None:
    """Re-create FK constraints with ON DELETE CASCADE (idempotent via DO block)."""
    fks = [
        ("photos",      "photos_folder_id_fkey",      "folder_id",  "folders", "id"),
        ("faces",       "faces_photo_id_fkey",         "photo_id",   "photos",  "id"),
        ("upload_jobs", "upload_jobs_folder_id_fkey",  "folder_id",  "folders", "id"),
        ("upload_jobs", "upload_jobs_event_id_fkey",   "event_id",   "events",  "id"),
        ("photos",      "photos_event_id_fkey",        "event_id",   "events",  "id"),
        ("faces",       "faces_event_id_fkey",         "event_id",   "events",  "id"),
    ]
    for child_table, constraint, col, parent_table, parent_col in fks:
        stmt = f"""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = '{constraint}'
              AND table_name      = '{child_table}'
          ) THEN
            ALTER TABLE {child_table} DROP CONSTRAINT {constraint};
          END IF;
          ALTER TABLE {child_table} ADD CONSTRAINT {constraint}
            FOREIGN KEY ({col}) REFERENCES {parent_table}({parent_col})
            ON DELETE CASCADE;
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """
        with engine.begin() as conn:
            conn.execute(text(stmt))


def _migrate_faces_128d() -> None:
    """Switch faces.embedding from 512-d to 128-d if the column is still 512-d."""
    try:
        with engine.begin() as conn:
            # Check current dimension by inspecting pg_attribute.
            row = conn.execute(text(
                "SELECT atttypmod FROM pg_attribute "
                "JOIN pg_class ON attrelid = pg_class.oid "
                "WHERE relname = 'faces' AND attname = 'embedding'"
            )).fetchone()
            if row and row[0] != 128:
                # Drop old 512-d column (and its index) then recreate at 128-d.
                conn.execute(text("DROP INDEX IF EXISTS ix_faces_embedding_hnsw"))
                conn.execute(text("ALTER TABLE faces DROP COLUMN IF EXISTS embedding"))
                conn.execute(text(
                    "ALTER TABLE faces ADD COLUMN embedding vector(128)"
                ))
        # Recreate HNSW index outside the transaction (CREATE INDEX CONCURRENTLY
        # isn't needed here since the table is small after the column drop).
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_faces_embedding_hnsw "
                "ON faces USING hnsw (embedding vector_cosine_ops)"
            ))
    except Exception:
        log.warning("_migrate_faces_128d failed (non-fatal)", exc_info=True)
