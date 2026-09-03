"""FastAPI application factory and entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import StorageError
from app.routers import admin_events, admin_photos, auth, guest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    import app.core.database as db
    try:
        init_db()
        db.LAST_INIT_ERROR = None
        logger.info("Database initialized successfully.")
    except Exception as exc:  # noqa: BLE001
        db.LAST_INIT_ERROR = f"{type(exc).__name__}: {exc}"
        logger.exception("Database initialization failed on startup.")
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="photoEvent API",
        version="2.0.0-afd047e",
        description="Event photo sharing with AI facial recognition.",
        lifespan=lifespan,
    )

    # CORS: allow comma-separated FRONTEND_ORIGIN list plus any *.vercel.app
    # preview deployment, so both localhost and Vercel prod/preview work.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Translate storage backend failures into a clear 502 (Bad Gateway) response.
    # This runs after the CORS middleware, so CORS headers are still attached and
    # the browser sees a proper JSON error instead of a misleading CORS failure.
    @app.exception_handler(StorageError)
    async def storage_error_handler(_: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": exc.message,
                "upstream_status": exc.upstream_status,
                "error": "storage_backend_error",
            },
        )

    # Register routers.
    app.include_router(auth.router)
    app.include_router(admin_events.router)
    app.include_router(admin_photos.router)
    app.include_router(guest.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        """Liveness probe — also shows DB init error and version."""
        import app.core.database as db
        return {
            "status": "ok",
            "version": "2.0.0-afd047e",
            "init_error": getattr(db, "LAST_INIT_ERROR", None),
        }

    return app


app = create_app()
