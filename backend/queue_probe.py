"""Local fixed probe submission; intentionally no HTTP task-execution endpoint."""

import argparse
from uuid import UUID, uuid4

from core.database import SessionLocal
from models.database import User
from models.operation_schemas import ProbeInput
from services.operation_service import create_probe
from services.policy_service import PolicyError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Queue a SIMULATED internal probe as an existing operator"
    )
    parser.add_argument("--actor-id", required=True, type=int)
    parser.add_argument("--application-id", required=True, type=UUID)
    parser.add_argument("--binding-id", required=True, type=UUID)
    parser.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        actor = db.get(User, args.actor_id)
        if actor is None:
            parser.exit(1, "Existing active operator required\n")
        try:
            operation = create_probe(
                db,
                actor,
                args.application_id,
                args.binding_id,
                ProbeInput(),
                args.idempotency_key,
                str(uuid4()),
            )
        except PolicyError as exc:
            parser.exit(1, f"{exc.message}\n")
        print(f"SIMULATED operation {operation.id}: {operation.status}")


if __name__ == "__main__":
    main()
