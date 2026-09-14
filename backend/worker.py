"""Separate polling worker: python -m worker [--once]."""

import argparse
import logging
import signal
from threading import Event, Thread
from uuid import uuid4

from core.config import get_settings
from core.database import SessionLocal
from models.operation_schemas import ProbeInput
from services.environment_service import require_local_simulation
from services.policy_service import PolicyError
from services.queue_service import (
    Claim,
    LostLease,
    Outcome,
    authorize,
    claim,
    finish,
    heartbeat,
)
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def probe(item: Claim, cancelled: Event, lost: Event) -> Outcome:
    """Fixed deterministic, side-effect-free handler. No user code or providers."""
    data = ProbeInput.model_validate(item.payload)
    if item.phase == "reconcile":
        # There are no external effects to repeat. Unknown deliberately exercises
        # unresolved provider semantics, without pretending to resolve them.
        return "unknown" if data.scenario == "unknown" else "safe_to_retry"
    for _ in range(data.delay_seconds * 10):
        if lost.wait(0.1):
            raise LostLease()
        if cancelled.is_set():
            return "cancelled"
    if cancelled.is_set():
        return "cancelled"
    if data.scenario == "transient" and item.attempt_count < 3:
        return "transient"
    return {
        "success": "succeeded",
        "transient": "succeeded",
        "terminal": "failed",
        "unknown": "unknown",
    }[data.scenario]  # type: ignore[return-value]


def run_one(
    sessions: sessionmaker[Session],
    worker_id: str,
    lease_seconds: int = 30,
    kinds: tuple[str, ...] | None = None,
) -> bool:
    with sessions() as db:
        item = claim(db, worker_id, lease_seconds, kinds)
    if item is None:
        return False
    stopped, cancelled, lost = Event(), Event(), Event()

    def pulse() -> None:
        while not stopped.wait(lease_seconds / 3):
            try:
                with sessions() as db:
                    if heartbeat(db, item, lease_seconds):
                        cancelled.set()
            except Exception:
                lost.set()
                return

    thread = Thread(target=pulse, daemon=True)
    thread.start()
    diagnostic: str | None
    outcome: Outcome
    delivery_result: tuple[str, int, str, str] | None = None
    try:
        with sessions() as db:
            if heartbeat(db, item, lease_seconds):
                cancelled.set()
        with sessions() as db:
            authorize(db, item)
        # Explicit dispatch; no dynamic imports, shell commands or task endpoint.
        if item.kind in {"generate_bundle", "validate_offline"}:
            from services.delivery_service import execute, store

            if cancelled.is_set():
                outcome, diagnostic = "cancelled", None
            elif item.phase == "reconcile":
                # Only immutable local files may have been published. DB results
                # commit with terminal state, so another attempt is safe.
                outcome, diagnostic = "safe_to_retry", None
            else:
                with sessions() as db:
                    content, media_type, verdict = execute(db, item.operation_id)
                digest = store().put(content)
                delivery_result = (digest, len(content), media_type, verdict)
                outcome, diagnostic = "succeeded", None
        elif item.kind != "queue_probe":
            outcome = "failed"
            diagnostic = "unsupported_handler"
        else:
            outcome = probe(item, cancelled, lost)
            diagnostic = "probe_rejected" if outcome == "failed" else None
    except LostLease:
        return True
    except PolicyError:
        # An uncertain prior attempt is not made safe by revoking its requester.
        outcome = "unknown" if item.phase == "reconcile" else "failed"
        diagnostic = "authorization_changed"
    except Exception:
        outcome, diagnostic = (
            (
                "transient"
                if item.kind in {"generate_bundle", "validate_offline"}
                else "unknown"
            ),
            "handler_error",
        )
    finally:
        stopped.set()
        thread.join()
    if not lost.is_set():
        try:
            with sessions() as db:
                finish(
                    db,
                    item,
                    outcome,
                    diagnostic=diagnostic,
                    delivery_result=delivery_result,
                )
        except LostLease:
            pass
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the simulated durable operation worker"
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    require_local_simulation(get_settings())
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    worker_id = str(uuid4())
    logging.basicConfig(level=logging.INFO)
    logger.info("Simulated worker started: %s", worker_id)
    while not stopped.is_set():
        try:
            worked = run_one(SessionLocal, worker_id)
        except Exception:
            # Do not log raw DB URLs, payloads or exception strings.
            logger.error("Worker database cycle failed; will reconnect")
            if args.once:
                raise SystemExit(1) from None
            worked = False
        if args.once:
            break
        if not worked:
            stopped.wait(1)


if __name__ == "__main__":
    main()
