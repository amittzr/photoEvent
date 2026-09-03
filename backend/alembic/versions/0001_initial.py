"""Initial schema: events, folders, photos, faces + pgvector index.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMB_DIM = settings.FACE_EMBEDDING_DIM


def upgrade() -> None:
    # Ensure the pgvector extension exists (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_events_slug", "events", ["slug"], unique=True)

    op.create_table(
        "folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_folders_event_id", "folders", ["event_id"])

    op.create_table(
        "photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("thumb_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("drive_original_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("drive_thumb_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_photos_folder_id", "photos", ["folder_id"])
    op.create_index("ix_photos_event_id", "photos", ["event_id"])

    op.create_table(
        "faces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(EMB_DIM), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("det_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_faces_photo_id", "faces", ["photo_id"])
    op.create_index("ix_faces_event_id", "faces", ["event_id"])

    # HNSW index for fast approximate nearest-neighbor search via cosine distance.
    op.execute(
        "CREATE INDEX ix_faces_embedding_hnsw ON faces "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_faces_embedding_hnsw", table_name="faces")
    op.drop_index("ix_faces_event_id", table_name="faces")
    op.drop_index("ix_faces_photo_id", table_name="faces")
    op.drop_table("faces")

    op.drop_index("ix_photos_event_id", table_name="photos")
    op.drop_index("ix_photos_folder_id", table_name="photos")
    op.drop_table("photos")

    op.drop_index("ix_folders_event_id", table_name="folders")
    op.drop_table("folders")

    op.drop_index("ix_events_slug", table_name="events")
    op.drop_table("events")
