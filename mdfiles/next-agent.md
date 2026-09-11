# Agent handoff

Inspect Git status, preserve unrelated changes, verify prerequisites on updated
main, and read AGENTS.md before creating the next task branch. This handoff
records implementation; it does not imply that its PR has merged.

## Implemented state

T01–T03 are merged. T03 PR #8 was confirmed merged at
`46a9cd9194ea4384d281c956b61eca493cac830a`. T04 is implemented on its own branch
from that updated main and awaits review/merge. T05 has not started.
AI/chat/RAG/LLM/inference remain removed; historical tables/migrations are retained.

The platform has development accounts, explicit local admin bootstrap,
teams/memberships, owned applications, direct/team roles, versioned metadata and
simulated environment bindings, filtered paginated reads and transactional audit.
Local configuration requires `RUNTIME_PROFILE=local` and explicit
`DEPLOYMENT_EXECUTOR=simulated`. Organization and real sandbox execution fail at
startup. The user’s `.env` was not changed.

T04 adds:

- Migration `007_durable_operations`: operations, attempts, binding reservations,
  idempotency command history, internal queue probe request/results, and worker
  heartbeats. UUID/UTC metadata and noncascading references preserve existing data.
- Synchronous command transactions atomically create request, operation,
  reservation, command hash and audit. Idempotency scope is actor/action/target/key;
  identical repeats return the original operation/current state, mismatches 409.
  Reads require current application visibility. Cancel/retry/reconcile and probe
  submission require an explicit current operator role, including for admins.
- `python -m worker` is independent of FastAPI; Compose includes a worker service.
  Short PostgreSQL `FOR UPDATE SKIP LOCKED` claims persist attempt/correlation,
  worker UUID, monotonic fencing token and 30-second lease. Separate-session
  heartbeats renew every 10 seconds. Idle polling publishes worker freshness.
- Worker authorization rechecks the requester’s active account, direct/team
  operator grant, application lifecycle, current binding version, environment
  enablement/executor and approved target before handling. Handlers hold no DB
  transaction. All operation/attempt/result/reservation/audit writes are fenced,
  including rollback if the lease expires during result flush.
- Only the typed `queue_probe` handler exists. It is explicitly simulated and
  has no external side effects. Closed payload schema 1 has deterministic success,
  transient, terminal and unknown scenarios for tests. The local CLI exposes only
  the success probe; no HTTP arbitrary task execution endpoint exists.
- Known safe failures retry at most three executions, with jittered exponential
  delay (2-second base, 60-second cap). Lease expiry always enters reconciliation;
  the probe establishes no external effects before scheduling a safe retry.
  Unknown outcomes become `needs_attention` and retain the binding reservation.
- Cancellation before claim immediately prevents execution; running cancellation
  is intent until observed, and observed success may win. Retry creates a new
  linked operation after renewed policy checks. Reconcile requires an operator
  reason, schedules observation, and never forces an outcome. Only its hash is
  retained, avoiding pasted secret text in history.
- Status/list/attempt and cancel/retry/reconcile APIs, Streamlit operation history,
  refresh/freshness and recovery controls. Responses omit payloads, worker tokens
  and raw exception messages. `/health` is API liveness; `/ready` requires queue
  access plus a worker pulse within 60 seconds. Admin-only `/api/v1/queue/telemetry`
  exposes state counts, oldest eligible age, expired leases and live worker count.

## Verification performed

- `uv run --locked pytest -q`: **126 passed**, including queue state/API/UI,
  current authorization, transaction failures, stale leases before and during
  result flush, bounded retries, sanitized diagnostics and prior T01–T03 coverage.
  Network blocking remained enabled; TestClient ran outside this sandbox's thread
  restriction. The UI workflow asserts the actual attempt outcome column.
- `uv run --locked mypy`: **32 source files passed**.
- Ruff lint and format: clean over the complete README/CI scope, **53 files**.
- `uv run --locked pytest tests/integration -q -rs`: **15 skipped** locally because
  `TEST_DATABASE_URL` is unset. These skips do not establish PostgreSQL behavior.
  Separate-process contention/restart, heartbeat/cancel, migration round trip,
  concurrent submission, fencing and rollback tests await hosted verification.
- Hosted T04 CI has not yet been run. Review current results before merge.

## Remaining work and limitations

- Review T04 and current CI before merge. PostgreSQL tests must actually pass;
  SQLite cannot establish concurrent claim or process recovery behavior.
- No local devstack exists at `~/code/devstack`; the Docker executable fails with
  an input/output error. Live Compose startup and image builds are unverified.
- The probe only exercises infrastructure. No generated bundle, artifact store,
  revision, approval, deployment, GitHub or Databricks adapter exists yet. No real
  provider, paid workload or infrastructure activation was attempted.
- Unknown probe scenarios intentionally remain unresolved after reconciliation.
  There is no force-success/reservation-release API. Future real handlers need
  provider-specific correlation, reconciliation and outcome evidence.
- Binding reservations are implemented; future provider workspace concurrency
  limits and provider submission deduplication are not applicable to this probe.
  No exactly-once external execution claim is made.
- Worker heartbeat rows and operation/idempotency history are retained. Retention,
  richer metrics/exporters and organization identity remain later work.

## Next task

Verify T04 is merged on updated main, then implement **T05 — Generate a bundle and
capture a revision**, on its own branch. Read its full scope and acceptance tests;
do not begin T06 or real provider work. Extend the closed handler/schema/migration
contracts deliberately; do not introduce arbitrary shell/repository execution.

## Files to read first

- `AGENTS.md`, `mdfiles/README.md`, T05 in `mdfiles/development-plan.md`.
- `mdfiles/integrations.md`, `mdfiles/domain-contracts.md`, `mdfiles/api-contracts.md`,
  `mdfiles/architecture.md`, `mdfiles/testing-and-operation.md`.
- `backend/models/operations.py`, `operation_schemas.py`, and migration 007.
- `backend/services/operation_service.py`, `queue_service.py`, `backend/worker.py`.
- `backend/services/environment_service.py`, `backend/api/endpoints/operations.py`.
- `tests/unit/test_operations.py`, `tests/integration/test_operations.py`,
  `frontend/operation_ui.py`, root README and CI.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md and mdfiles/next-agent.md. Inspect Git status and
verify T04 is merged into updated main. Create a task branch if needed and implement
T05 only: generated bundle/artifact capture, immutable revision and offline
validation, using the durable worker. Preserve unrelated changes, explain the plan,
run applicable checks, update the handoff/contracts/map and open a draft PR. Do not
merge, start T06, execute arbitrary adopted repository code, or activate providers.
