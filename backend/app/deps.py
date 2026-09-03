"""Dependency-injection wiring for repositories, services, auth, and storage."""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.repositories.event_repository import EventRepository
from app.repositories.face_repository import FaceRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.photo_repository import PhotoRepository
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.face_service import FaceService
from app.services.search_service import SearchService
from app.services.storage_service import StorageService
from app.services.upload_service import UploadService

SessionDep = Annotated[Session, Depends(get_session)]

_bearer = HTTPBearer(auto_error=True)


# --- Singletons (heavy / stateless) ---
@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


@lru_cache
def get_storage_service() -> StorageService:
    return StorageService()


@lru_cache
def get_face_service() -> FaceService:
    return FaceService()


# --- Auth guard ---
def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    """Validate the JWT bearer token and return the admin username."""
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject


AdminDep = Annotated[str, Depends(get_current_admin)]


# --- Per-request services (need a DB session) ---
def get_event_service(session: SessionDep) -> EventService:
    return EventService(
        EventRepository(session),
        FolderRepository(session),
        PhotoRepository(session),
    )


def get_upload_service(
    session: SessionDep,
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> UploadService:
    return UploadService(PhotoRepository(session), storage)


def get_search_service(
    session: SessionDep,
    face_service: Annotated[FaceService, Depends(get_face_service)],
) -> SearchService:
    return SearchService(
        EventRepository(session),
        FaceRepository(session),
        PhotoRepository(session),
        face_service,
    )
