"""Database engine and session management."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlmodel import Session

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
