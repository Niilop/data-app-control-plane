# backend/api/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from core.database import get_db
from models.schemas import UserCreate, UserLogin, Token, UserResponse
from services.auth_service import (
    create_user, authenticate_user, create_access_token, decode_token, get_user_by_email
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# This tells FastAPI where the client should send the login request to get a token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@router.post("/register", response_model=UserResponse)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user.
    
    - **email**: Must be a valid email address
    - **username**: Unique username
    - **password**: Password for the account
    """
    try:
        user = create_user(db, user_create)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form_data.username will now hold either the email or the username provided by the client
    user = authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Always use the user's actual email for the token payload, regardless of how they logged in
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token_data = decode_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user = get_user_by_email(db, token_data["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user
