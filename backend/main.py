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

    from api.endpoints import applications, auth, teams

    app.include_router(auth.router)
    app.include_router(applications.router)
    app.include_router(teams.router)

    @app.get("/")
    def root(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        return {"message": f"{settings.app_name} is running"}

    @app.get("/health")
    def health() -> dict[str, str]:
        """Process liveness only; does not claim database readiness."""
        return {"status": "ok"}

    return app


app = create_app()
