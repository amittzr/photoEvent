"""Admin router for event and folder management."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.deps import AdminDep, get_event_service
from app.schemas.event import EventCreate, EventOut, EventUpdate
from app.schemas.folder import FolderCreate, FolderOut
from app.services.event_service import EventService

router = APIRouter(prefix="/api/admin", tags=["admin:events"])

EventServiceDep = Annotated[EventService, Depends(get_event_service)]


@router.get("/events", response_model=list[EventOut])
def list_events(_: AdminDep, service: EventServiceDep) -> list[EventOut]:
    return service.list_events()


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    _: AdminDep, body: EventCreate, service: EventServiceDep
) -> EventOut:
    return service.create_event(body)


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    _: AdminDep,
    event_id: uuid.UUID,
    body: EventUpdate,
    service: EventServiceDep,
) -> EventOut:
    return service.update_event(event_id, body)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(_: AdminDep, event_id: uuid.UUID, service: EventServiceDep) -> None:
    service.delete_event(event_id)


@router.post(
    "/events/{event_id}/folders",
    response_model=FolderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_folder(
    _: AdminDep,
    event_id: uuid.UUID,
    body: FolderCreate,
    service: EventServiceDep,
) -> FolderOut:
    return service.create_folder(event_id, body)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(_: AdminDep, folder_id: uuid.UUID, service: EventServiceDep) -> None:
    service.delete_folder(folder_id)
