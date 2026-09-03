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
    """Application startup/shutdown.

    On startup, ensure the pgvector extension and all tables exist. This makes
    the app self-healing on databases where migrations haven't run (e.g. a fresh
    Neon PostgreSQL instance) without dropping any existing data.
    """
    try:
        init_db()
        logger.info("Database initialized (tables ensured).")
    except Exception:  # noqa: BLE001
        # Don't crash the whole app if init fails; log so it's visible in logs.
        logger.exception("Database initialization failed on startup.")
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="photoEvent API",
        # Bump on deploys so /openapi.json confirms the running build.
        version="1.1.0-drive-sync",
        description="Event photo sharing with AI facial recognition.",
        lifespan=lifespan,
    )

    # CORS: allow the configured frontend origin(s). Supports a comma-separated
    # list (e.g. localhost for dev + the deployed Vercel URL). Also allow any
    # *.vercel.app preview deployment via a regex so preview builds work too.
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
    def health() -> dict[str, str]:
        """Simple liveness probe."""
        return {"status": "ok"}

    return app


app = create_app()
