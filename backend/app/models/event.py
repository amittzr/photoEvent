"""Event model."""
import uuid
from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):
    """An event (e.g., a wedding) that groups folders and photos."""

    __tablename__ = "events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(nullable=False)
    slug: str = Field(nullable=False, unique=True, index=True)
    event_date: date | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
