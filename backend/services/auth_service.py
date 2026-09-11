# backend/services/auth_service.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from core.config import get_settings
from models.database import User
from models.schemas import UserCreate

settings = get_settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            return None
        return {"email": email}
    except JWTError:
        return None


def create_user(db: Session, user_create: UserCreate) -> User:
    """Create a new user in the database."""
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == user_create.email) | (User.username == user_create.username)
    ).first()
    
    if existing_user:
        raise ValueError("User with this email or username already exists")
    
    # Create new user
    db_user = User(
        email=user_create.email,
        username=user_create.username,
        password_hash=hash_password(user_create.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: Session, identifier: str, password: str) -> Optional[User]:
    """Authenticate a user by email OR username."""
    # Search for a match in either the email or username column
    user = db.query(User).filter(
        (User.email == identifier) | (User.username == identifier)
    ).first()
    
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get a user by email."""
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    return db.query(User).filter(User.id == user_id).first()
