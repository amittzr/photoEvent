"""SQLModel entities. Importing here ensures Alembic autogenerate sees all tables."""
from app.models.event import Event
from app.models.folder import Folder
from app.models.photo import Photo, PhotoStatus
from app.models.face import Face
from app.models.upload_job import UploadJob, JobStatus

__all__ = [
    "Event",
    "Folder",
    "Photo",
    "PhotoStatus",
    "Face",
    "UploadJob",
    "JobStatus",
]
