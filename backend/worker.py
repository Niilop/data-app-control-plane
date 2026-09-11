"""Separate polling worker: python -m worker [--once].

Runs simulated probes and real local delivery work (bundle generation and
offline validation). Local work is labelled `local`, never `simulated`; no
handler contacts a provider or executes adopted repository code.
"""

import argparse
import logging
import signal
from threading import Event, Thread
from uuid import uuid4

from core.config import get_settings
from core.database import SessionLocal
from models.operation_schemas import ProbeInput
from services.delivery_service import run_generation, run_validation
from services.environment_service import require_local_simulation
from services.policy_service import PolicyError
from services.queue_service import (
    Apply,
    Claim,
    LostLease,
    Outcome,
    authorize,
    claim,
    finish,
    heartbeat,
)
from services.template_service import GenerationError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)
HANDLERS = {
    "bundle_generation": run_generation,
    "offline_validation": run_validation,
}


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


def local_work(
    sessions: sessionmaker[Session], item: Claim
) -> tuple[Outcome, str | None, Apply | None]:
    """Deterministic local generation or offline validation; no provider, no user code.

    Repeating this work is always safe: rendering is deterministic and artifacts
    are content-addressed, so a lost lease can only leave identical bytes behind.
    """
    if item.phase == "reconcile":
        return "safe_to_retry", "local_work_repeatable", None
    try:
        with sessions() as db:
            return HANDLERS[item.kind](db, item.operation_id)
    except GenerationError as error:
        # A template or parameter defect is terminal; retrying cannot change it.
        return "failed", error.code, None
    except PolicyError as error:
        return "failed", error.code, None


def run_one(
    sessions: sessionmaker[Session], worker_id: str, lease_seconds: int = 30
) -> bool:
    with sessions() as db:
        item = claim(db, worker_id, lease_seconds)
    if item is None:
        return False
    stopped, cancelled, lost = Event(), Event(), Event()
    apply: Apply | None = None

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
    try:
        with sessions() as db:
            if heartbeat(db, item, lease_seconds):
                cancelled.set()
        with sessions() as db:
            authorize(db, item)
        # Explicit dispatch; no dynamic imports, shell commands or task endpoint.
        if item.kind == "queue_probe":
            outcome: Outcome = probe(item, cancelled, lost)
            diagnostic = "probe_rejected" if outcome == "failed" else None
        elif item.kind in HANDLERS:
            outcome, diagnostic, apply = local_work(sessions, item)
        else:
            outcome, diagnostic = "failed", "unsupported_handler"
    except LostLease:
        return True
    except PolicyError:
        # An uncertain prior attempt is not made safe by revoking its requester.
        outcome = "unknown" if item.phase == "reconcile" else "failed"
        diagnostic = "authorization_changed"
    except Exception:
        outcome, diagnostic = "unknown", "handler_error"
    finally:
        stopped.set()
        thread.join()
    if not lost.is_set():
        try:
            with sessions() as db:
                finish(db, item, outcome, diagnostic=diagnostic, apply=apply)
        except LostLease:
            pass
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the durable operation worker (simulated probes, local delivery)"
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    require_local_simulation(get_settings())
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    worker_id = str(uuid4())
    logging.basicConfig(level=logging.INFO)
    logger.info("Durable operation worker started: %s", worker_id)
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
