"""Switch face embeddings from 512-d (InsightFace) to 128-d (dlib).

Revision ID: 0004_faces_128d
Revises: 0002_jobs_thumb
Create Date: 2026-09-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_faces_128d"
down_revision: Union[str, None] = "0002_jobs_thumb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_faces_embedding_hnsw")
    op.execute("ALTER TABLE faces DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE faces ADD COLUMN embedding vector(128) NOT NULL DEFAULT array_fill(0, ARRAY[128])::vector")
    op.execute("ALTER TABLE faces ALTER COLUMN embedding DROP DEFAULT")
    op.execute("CREATE INDEX ix_faces_embedding_hnsw ON faces USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_faces_embedding_hnsw")
    op.execute("ALTER TABLE faces DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE faces ADD COLUMN embedding vector(512) NOT NULL DEFAULT array_fill(0, ARRAY[512])::vector")
    op.execute("ALTER TABLE faces ALTER COLUMN embedding DROP DEFAULT")
    op.execute("CREATE INDEX ix_faces_embedding_hnsw ON faces USING hnsw (embedding vector_cosine_ops)")
