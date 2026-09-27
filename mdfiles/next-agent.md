# Agent handoff

Inspect Git status, preserve unrelated work, verify prerequisites on updated main,
and read AGENTS.md before creating or continuing a task branch. Leave merging to
the user. This handoff describes proposed T06 code, not a merged T06 implementation.

## Implemented state

T01–T05 are merged. T05 PR #13 was verified merged on 2026-09-20 at
`8e419050c5069b97ac5b582e02378f77658f3e99`; the earlier handoff's unmerged status
was stale. T06 starts from that fetched main. The abandoned T05 branch and its
unfinished-work stash are preserved. Accounts/data and migrations 001–008 are
unchanged; AI/chat/RAG/LLM/inference remain removed.

T05 preparation remains: approved synthetic `python-batch:1.0.0`, canonical local
ZIP/artifact storage, immutable revisions and static offline validation. T06 adds
`009_simulated_deployments` with append-only approval evidence and deployment
history. The scope digest binds revision/source/artifact/template/config, complete
binding/environment policy/target, simulated executor/mode and one exact passed
validation report. Later decisions supersede older decisions only for the same
scope digest; later reports never rewrite existing evidence.

Approval requires an active approver. Submission requires developer plus operator.
Self-approval against either revision requester or deployment submitter requires an
enabled local environment policy and explicit acknowledgement; evidence and audit
record this exception. API and worker check current roles, actors, lifecycle,
template, binding snapshot, approval decision and report. Eligibility is refreshed
after blocking policy locks and checked again before successful completion.

Deployment submission, command idempotency, binding reservation and audit commit
together. The existing worker handles simulated success/partial failure with no
provider calls or generated-source execution. Related observations/status and
first-success application activation commit with the lease fence and audit.
Partial failure preserves simulated resource observations and prior success.
Queued cancellation updates deployment status; retry creates a linked new operation
and new deployment after current checks. Lost leases reconcile before safe replay;
unknown/revoked reconciliation conservatively retains reservations.

React's Preparation revision view includes exact-scope review, approval decisions,
explicit local self-approval acknowledgement and simulated deployment submission.
Deployments shows history, observations and per-binding last success. Existing
Operations provides attempts and recovery. All deployment results say simulated.
ADR-018 documents the implementation boundary. T07 has not begun.

## Verification performed

Local checks on 2026-09-20:

- `uv run --locked pytest -q`: **169 passed**, including 22 deployment cases, with
  the offline network guard. The final run includes exact-scope supersession,
  stale/mismatched report/revision, changed policy/config, revoked roles, inactive
  actors/targets, self-approval, duplicate/conflicting commands, partial failure,
  fencing/recovery, and submission/completion audit rollback.
- `uv run --locked pytest tests/integration -q`: **20 passed, no skips**, against
  a disposable pgvector/pg16 container on loopback port 55439, with a unique schema
  per test. Includes migration/ORM parity and legacy data preservation, immutable
  SQL approvals, concurrent duplicate/conflicting deployments, lease fencing and
  partial failure. The **3 deployment PostgreSQL tests passed again** after the
  final approval-supersession change; they include revocation while submission
  waits on the environment policy lock.
- `uv run --locked mypy`: **39 modules passed**. CI-scoped Ruff lint and format
  checks passed across **66 files**. No Python dependency/lock changes were needed.
- `uv run --locked python scripts/check_generated_project.py`: locked offline
  install in a fresh temporary project/cache and **2 stdlib tests passed**.
- Frontend lint, Prettier, TypeScript and Vite build passed locally and in the
  locked Docker browser image (`npm ci`). **11 Chromium workflows passed** against
  disposable real API/worker fixtures. The deployment workflow covers generation,
  validation, denied unacknowledged self-approval, approval, lost-response replay,
  successful simulation, partial failure and preserved last success. Desktop
  approval and 390px deployment screenshots were inspected.
- Production frontend image built. Isolated Compose nginx smoke passed routing,
  CSP, cookie login/reload, authenticated write, readiness and logout. It uses no
  application database/volume. After final backend policy changes, a focused
  browser rerun exposed a capture/query test race. The test now waits for save
  completion, and all **11 workflows passed again** (25.1s).
- Sandboxed FastAPI TestClient startup hung in its local event loop; tests passed
  outside that sandbox with the same offline network guard and disposable data.
  No global packages were installed. Existing deprecation warnings remain.
- Hosted CI is not claimed as passed in this handoff. Inspect the T06 draft's
  actual checks before merge. No real-provider or old-database migration check
  was run; neither is authorized by this task.

## Remaining work and limitations

- Review the T06 draft, schema/policy decisions and CI; only the user merges it.
  Local approval trusts the host/database administrator and does not implement
  organizational enforcement. Simulation cannot establish workspace readiness.
- The abandoned T05 database reportedly uses `008_bundle_generation`, whereas
  merged T05 uses `008_prepared_revisions`. **Do not stamp, reset, or automatically
  migrate that database.** Preserve it, the earlier branch and stash. Use an
  isolated database on the merged migration chain. Conversion requires separately
  agreed, inspected, data-preserving migration work. No conversion was attempted.
- Generated artifacts remain local immutable bytes. Back up the DB and artifact
  directory together; unreferenced-file cleanup remains deferred. Offline reports
  are static checks, not workspace validation or worker-executed project tests.
- Simulation has only fixed success/partial-failure fixtures. Its references are
  fabricated `simulated://` observations, never provider IDs. It cannot deploy
  via GitHub/Databricks, run a data job, grant permissions or provision resources.
- Approval decisions are synchronous, append-only and not idempotency-keyed.
  Inspect history after a lost approval response. Async UI command keys survive
  transport retries/dialog reopen in the signed-in workspace; reload clears them.
  Inspect deployment history before deliberate resubmission after reload.
- Existing session limitations remain: logout does not revoke copied JWTs.
  Organization SSO, token revocation and real provider enforcement are later work.

## Next task

Review T06 only and verify its draft CI. After user merge and a separate assignment,
implement **T07 only**: an allowlisted simulated job run from a successful deployment
and recorded run visibility. Inspect Git status, verify merged prerequisites on
updated main and create a new bounded task branch if needed. Do not start T07 merely
because T06 code is available; no real providers or infrastructure are authorized.

## Files to read first

- AGENTS.md; mdfiles/README.md; T06/T07 in development-plan.md; ADR-018 in decisions.md.
- mdfiles/domain-contracts.md, api-contracts.md, architecture.md, integrations.md.
- backend/models/deployment.py, deployment_schemas.py;
  backend/alembic/versions/009_simulated_deployments.py.
- backend/services/deployment_service.py, queue_service.py, operation_service.py,
  delivery_service.py; backend/worker.py; integrations/simulated_deployment.py.
- backend/api/endpoints/deployments.py; frontend/src/pages/deployments.tsx,
  preparation.tsx; frontend/e2e/workflows.spec.ts.
- tests/unit/test_deployments.py, tests/integration/test_deployments.py,
  test_migrations.py; tests/browser_server.py; .github/workflows/ci.yml.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md and mdfiles/next-agent.md. Inspect Git status and
preserve unrelated changes, the abandoned T05 branch/stash and its old database.
Verify T05 PR #13's merged commit and the current T06 draft/CI against updated main.
Review T06 only for exact approval scope, current authorization, explicit audited
self-approval, transactionality, simulation labels, leases/fencing and recovery.
Use an isolated database; do not stamp/reset/migrate the old 008_bundle_generation
history. Leave merging to the user. Do not begin T07 or activate external providers.
