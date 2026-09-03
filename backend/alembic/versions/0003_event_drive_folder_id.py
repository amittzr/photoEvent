"""Add events.drive_folder_id for linking an existing Drive folder.

Revision ID: 0003_drive_folder
Revises: 0002_jobs_thumb
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_drive_folder"
down_revision: Union[str, None] = "0002_jobs_thumb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "drive_folder_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("events", "drive_folder_id")
