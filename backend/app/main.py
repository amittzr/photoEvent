"""FastAPI application factory and entrypoint."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import StorageError
from app.routers import admin_events, admin_photos, auth, guest


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="photoEvent API",
        version="1.0.0",
        description="Event photo sharing with AI facial recognition.",
    )

    # CORS: allow the configured frontend origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
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
