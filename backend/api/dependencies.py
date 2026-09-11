"""Resolve current database identity on every request, including old JWTs."""

from api.browser_session import SESSION_COOKIE, require_browser_request
from core.database import get_db
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from models.database import User
from services.auth_service import decode_token, get_user_by_email
from services.policy_service import require_active, require_admin
from sqlalchemy.orm import Session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_actor(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if token is None:
        token = request.cookies.get(SESSION_COOKIE)
        if token and request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_browser_request(request)
    if not token:
        raise HTTPException(
            401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    data = decode_token(token)
    user = get_user_by_email(db, data["email"]) if data else None
    if user is None:
        raise HTTPException(
            401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    require_active(user)
    return user


def get_admin(actor: User = Depends(get_actor)) -> User:
    require_admin(actor)
    return actor
