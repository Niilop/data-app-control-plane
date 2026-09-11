"""Explicit local simulated environment seed; never deploys or creates accounts."""

import argparse
from uuid import uuid4

from core.config import get_settings
from core.database import SessionLocal
from models.database import User
from models.environment_schemas import EnvironmentCreate
from models.platform import Environment
from services.environment_service import create_environment, require_local_simulation
from services.policy_service import PolicyError, require_admin
from sqlalchemy import select
from sqlalchemy.orm import Session


def seed_sandbox(
    db: Session, actor: User, *, allow_self_approval: bool = False
) -> Environment:
    require_admin(actor)
    require_local_simulation(get_settings())
    data = EnvironmentCreate(
        name="local-sandbox",
        workspace_ref="simulated://local-sandbox",
        allowed_executor="simulated",
        enabled=True,
        allow_self_approval=allow_self_approval,
        allowed_bundle_targets=["sandbox"],
    )
    existing = db.scalar(select(Environment).where(Environment.name == data.name))
    if existing is not None:
        if any(
            getattr(existing, key) != value for key, value in data.model_dump().items()
        ):
            raise PolicyError(
                409,
                "seed_conflict",
                "Existing sandbox differs; review it through environment administration",
            )
        return existing
    return create_environment(db, actor, data, str(uuid4()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-user-id", required=True, type=int)
    parser.add_argument(
        "--allow-self-approval",
        action="store_true",
        help="Explicit local-only opt-in; disabled by default",
    )
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            actor = db.get(User, args.admin_user_id)
            if actor is None:
                parser.exit(1, "Administrator does not exist\n")
            environment = seed_sandbox(
                db, actor, allow_self_approval=args.allow_self_approval
            )
            print(
                f"Simulated sandbox: {environment.id}; self-approval: {environment.allow_self_approval}"
            )
    except PolicyError as exc:
        parser.exit(1, exc.message + "\n")


if __name__ == "__main__":
    main()
