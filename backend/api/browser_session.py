"""Same-origin browser sessions; bearer API clients retain their existing contract."""

from core.config import get_settings
from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "control_plane_session"


def require_browser_request(request: Request) -> None:
    """A custom header prevents simple-form CSRF; also require an exact trusted origin."""
    origin = request.headers.get("origin")
    own_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    trusted = {own_origin, *get_settings().cors_origins}
    if request.headers.get("x-control-plane") != "browser" or origin not in trusted:
        raise HTTPException(403, "Untrusted browser request")


def set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_settings().access_token_expire_minutes * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
