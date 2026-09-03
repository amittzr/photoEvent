"""Add upload_jobs table and make photos.drive_thumb_id nullable.

Revision ID: 0002_jobs_thumb
Revises: 0001_initial
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_jobs_thumb"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Thumbnails now live on local disk (WebP); Drive thumb id is optional.
    op.alter_column("photos", "drive_thumb_id", nullable=True)

    op.create_table(
        "upload_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_upload_jobs_event_id", "upload_jobs", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_upload_jobs_event_id", table_name="upload_jobs")
    op.drop_table("upload_jobs")
    op.alter_column("photos", "drive_thumb_id", nullable=False)
