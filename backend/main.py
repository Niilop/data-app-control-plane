"""FastAPI assembly for the local control plane."""

from api.platform_errors import install_errors
from core.config import Settings, get_settings
from core.rate_limit import limiter
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def handle_rate_limit(request: Request, exc: Exception) -> Response:
    """Adapt SlowAPI to Starlette's exception handler contract."""
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    return _rate_limit_exceeded_handler(request, exc)


def create_app() -> FastAPI:
    """Assemble the local platform API."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    install_errors(app)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, handle_rate_limit)
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    from api.endpoints import (
        applications,
        auth,
        delivery,
        environments,
        operations,
        teams,
    )

    app.include_router(auth.router)
    app.include_router(applications.router)
    app.include_router(teams.router)
    app.include_router(environments.router)
    app.include_router(operations.router)
    app.include_router(delivery.router)

    @app.get("/")
    def root(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        return {"message": f"{settings.app_name} is running"}

    @app.get("/health")
    def health() -> dict[str, str]:
        """Process liveness only; does not claim database readiness."""
        return {"status": "ok"}

    from api.endpoints.applications import DB

    @app.get("/ready")
    def ready(db: DB, response: Response) -> dict[str, str]:
        """Readiness requires the queue schema and a recent worker database pulse."""
        from datetime import timedelta

        from models.operations import Operation, WorkerHeartbeat
        from services.queue_service import now
        from sqlalchemy import select

        try:
            db.execute(select(Operation.id).limit(1))
            live = db.scalar(
                select(WorkerHeartbeat.worker_id)
                .where(WorkerHeartbeat.seen_at >= now(db) - timedelta(seconds=60))
                .limit(1)
            )
            if live:
                return {"status": "ready"}
        except Exception:
            db.rollback()
        response.status_code = 503
        return {"status": "unavailable"}

    return app


app = create_app()
