"""Explicit local account creation; secrets are prompted, never defaulted."""

import argparse
from getpass import getpass
from uuid import uuid4

from core.database import SessionLocal
from models.database import User
from models.schemas import UserCreate
from services.application_service import transaction
from services.audit_service import record_audit
from services.auth_service import hash_password
from sqlalchemy import select
from sqlalchemy.orm import Session


def bootstrap_account(db: Session, data: UserCreate, *, admin: bool = False) -> User:
    """Create a new account and audit local administrative intent atomically."""
    with transaction(db):
        if db.scalar(
            select(User).where(
                (User.email == data.email) | (User.username == data.username)
            )
        ):
            raise ValueError(
                "Account already exists; bootstrap does not overwrite accounts"
            )
        user = User(
            email=str(data.email),
            username=data.username,
            password_hash=hash_password(data.password),
            is_active=True,
            is_platform_admin=admin,
        )
        db.add(user)
        db.flush()
        record_audit(
            db,
            None,
            str(uuid4()),
            "user.bootstrapped",
            "user",
            user.id,
            {"is_platform_admin": admin, "is_active": True},
        )
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Explicitly grant local platform administrator",
    )
    args = parser.parse_args()
    password = getpass("New account password: ")
    if password != getpass("Repeat password: "):
        parser.exit(1, "Passwords do not match\n")
    try:
        data = UserCreate(email=args.email, username=args.username, password=password)
        with SessionLocal() as db:
            user = bootstrap_account(db, data, admin=args.admin)
            print(
                f"Created local user ID {user.id}; platform admin: {bool(user.is_platform_admin)}"
            )
    except ValueError:
        parser.exit(1, "Invalid account fields or account already exists\n")


if __name__ == "__main__":
    main()
