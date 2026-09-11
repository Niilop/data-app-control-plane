"""Compatible development registration/login with centralized active identity."""

from api.browser_session import SESSION_COOKIE, require_browser_request, set_session
from api.dependencies import get_actor
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from models.database import User
from models.schemas import Token, UserCreate, UserResponse
from services.auth_service import authenticate_user, create_access_token, create_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse)
def register(
    user_create: UserCreate, request: Request, db: Session = Depends(get_db)
) -> User:
    try:
        return create_user(db, user_create, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> dict[str, str]:
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    return {
        "access_token": create_access_token(data={"sub": user.email}),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def get_current_user(actor: User = Depends(get_actor)) -> User:
    return actor


@router.post("/session", response_model=UserResponse)
def browser_login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> User:
    require_browser_request(request)
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    set_session(response, request, create_access_token(data={"sub": user.email}))
    return user


@router.delete("/session", status_code=204)
def browser_logout(request: Request) -> Response:
    # Permit logout of an expired session; the browser still must pass CSRF checks.
    require_browser_request(request)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response
