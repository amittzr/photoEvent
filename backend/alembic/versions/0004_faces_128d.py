"""Switch face embeddings from 512-d (InsightFace) to 128-d (face_recognition/dlib).

The dimension is baked into the pgvector column type and the HNSW index so the
table must be recreated. All existing face vectors (512-d) are dropped.

Revision ID: 0004_faces_128d
Revises: 0003_drive_folder
Create Date: 2026-09-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_faces_128d"
down_revision: Union[str, None] = "0003_drive_folder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_DIM = 128
OLD_DIM = 512


def upgrade() -> None:
    # Drop the old 512-d faces table (including its HNSW index and FK constraints).
    op.drop_index("ix_faces_embedding_hnsw", table_name="faces", if_exists=True)
    op.drop_index("ix_faces_event_id", table_name="faces", if_exists=True)
    op.drop_index("ix_faces_photo_id", table_name="faces", if_exists=True)
    op.drop_table("faces")

    # Recreate with 128-d vector column.
    op.create_table(
        "faces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(NEW_DIM), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("det_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_faces_photo_id", "faces", ["photo_id"])
    op.create_index("ix_faces_event_id", "faces", ["event_id"])

    # Rebuild the HNSW index for 128-d cosine similarity search.
    op.execute(
        "CREATE INDEX ix_faces_embedding_hnsw ON faces "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_faces_embedding_hnsw", table_name="faces")
    op.drop_index("ix_faces_event_id", table_name="faces")
    op.drop_index("ix_faces_photo_id", table_name="faces")
    op.drop_table("faces")

    # Recreate 512-d version.
    op.create_table(
        "faces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(OLD_DIM), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("det_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_faces_photo_id", "faces", ["photo_id"])
    op.create_index("ix_faces_event_id", "faces", ["event_id"])
    op.execute(
        "CREATE INDEX ix_faces_embedding_hnsw ON faces "
        "USING hnsw (embedding vector_cosine_ops)"
    )
