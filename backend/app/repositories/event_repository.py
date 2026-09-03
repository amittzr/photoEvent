"""Data-access layer for events."""
import uuid

from sqlmodel import Session, select

from app.models.event import Event


class EventRepository:
    """Encapsulates all DB operations for the Event entity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, event: Event) -> Event:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def get(self, event_id: uuid.UUID) -> Event | None:
        return self.session.get(Event, event_id)

    def get_by_slug(self, slug: str) -> Event | None:
        return self.session.exec(select(Event).where(Event.slug == slug)).first()

    def list_all(self) -> list[Event]:
        return list(self.session.exec(select(Event).order_by(Event.created_at.desc())))

    def update(self, event: Event) -> Event:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def delete(self, event: Event) -> None:
        self.session.delete(event)
        self.session.commit()
