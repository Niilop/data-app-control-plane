# Agent handoff

Inspect Git status, preserve unrelated work, verify prerequisites on updated main,
and read AGENTS.md before creating or continuing a task branch. Leave merging to
the user. T07 is implemented for review; this handoff does not claim its PR is merged.

## Implemented state

T01–T06 are merged. T06 PR #14 was verified merged on 2026-09-27 at
`004b363dbeaeb34e4f8b20870fff60226ee00118`, through fetched main and GitHub metadata.
Its reported Platform CI and handoff checks succeeded. T07 starts from that main.
The old T05 database, abandoned branch and stash remain preserved. Migrations
001–009 and existing accounts/data are unchanged; AI features remain removed.

T07 adds `010_simulated_job_runs`, separate JobRun records and the closed
`run_simulated` operation. An active operator can run the ready `synthetic_job`
from a successful simulated deployment, with strict row_count 1–10,000 and explicit
success/failure fixtures. Developer/admin/owner status alone does not authorize runs.
Current actor, lifecycle, unchanged binding policy, active template and job readiness
are checked at submission, worker authorization and successful completion, including
after policy-lock waits. Prior deployment approval is historical evidence; a run
is not another deployment and does not require renewed approval or the former
approver/deployer to retain roles. ADR-019 records this boundary.

Submission atomically persists run/operation/reservation/key/audit. Runs share the
existing one-unresolved-operation-per-binding constraint. The fixed simulator has
no external effects and executes no source. Fenced completion verifies synthetic
row count/total; failure cannot change deployment status or last success. Responses
carry simulated mode, null provider run ID and recorded UTC observation times.
Cancellation updates queued runs; retry creates linked new operation/run records.
Lease expiry reconciles before safe replay; unknown/revoked reconciliation retains
reservations, with no force-success path.

React's Deployments view provides run controls and history. Overview shows recorded
revisions, approval evidence, deployments, run output and operation history. Public
reads use authorized DB state with existing pagination, not provider polling.
OperationResponse now includes the T06 deployment kind as well as the new run kind,
fixing deployment operation/history serialization. No dependencies or lock changes.

## Verification performed

Local checks on 2026-09-27:

- `uv run --locked pytest -q`: **190 passed**, including **21 run cases** for
  input/role/policy checks, output verification, replay, atomicity, cancellation,
  retry/fencing and uncertain-run reservation retention after revocation.
- `uv run --locked pytest tests/integration -q`: **23 passed, no skips**, against
  a disposable pgvector/pg16 container on loopback 55439, with unique schemas.
  Includes fresh migration/ORM parity, legacy preservation, upgrade from 009 with
  deployment evidence, downgrade refusal with run history, concurrent duplicate/
  conflicting run requests, stale fencing and revocation during a policy-lock wait.
- CI-scoped Ruff lint/format: **74 files passed**. `uv run --locked mypy`: **44
  modules passed**. Final added recovery test was separately linted/formatted.
- `uv run --locked python scripts/check_generated_project.py`: locked offline
  installation in an isolated temporary project and **2 stdlib tests passed**.
- Locked Docker browser image built (`npm ci`). Frontend lint/format/types/build
  and **12 Chromium workflows passed** (26.2s). The run test covers success/failure,
  lost-response same-key replay, dashboard evidence/output, mobile overflow and
  revoked operator controls. Desktop/mobile screenshots were inspected; desktop
  run-detail crowding prompted a small CSS fix. Frontend checks and the focused run
  browser workflow **passed again** (1 test, 6.3s) with the final layout.
- Production frontend image built. Isolated Compose nginx smoke **passed** routing,
  CSP, cookie login/reload, authenticated write, readiness and logout. This preceded
  the final run-detail CSS change; routing/session behavior was not changed by it.
- Python commands ran outside the sandbox because uv cache writes are blocked
  inside it; Docker also required socket access. All test data was disposable.
  No global packages were installed. Existing deprecation warnings remain.
- No real-provider work, application-database migration, or abandoned-database
  conversion was run. Hosted T07 CI is not claimed passed here; inspect the draft's
  actual checks before merging.

## Remaining work and limitations

- Review T07, ADR-019 and draft CI; only the user merges. All run results are local
  simulation. No real compute, GitHub/Databricks integration or scheduling exists.
- The abandoned T05 database reportedly uses `008_bundle_generation`, whereas
  main uses `008_prepared_revisions`. **Do not stamp, reset or automatically migrate
  that database.** Preserve it, the abandoned branch and stash. Use an isolated
  database on the merged chain; conversion requires separately inspected,
  data-preserving migration work.
- Runs conservatively serialize with all unresolved work on the same binding.
  Historical successful deployments can supply runs while their captured binding/
  template remains current; real resource drift and provider mapping remain T10.
- Overview lists are separately refreshed paginated histories, not a single atomic
  snapshot or live provider dashboard. Approval history is evidence, not a claim
  that every old decision remains currently executable.
- Run keys survive transport retries and dialog close/reopen on the same mounted
  deployment screen. Leaving that screen/reloading starts new form state; inspect
  history before repeating uncertain work. A successful submit starts a new intent
  so another deliberate identical run is possible.
- Existing limitations remain: local DB/host administrators are trusted; logout
  does not revoke copied JWTs; artifacts require backups alongside the DB;
  offline validation is not workspace validation. External identity/enforcement,
  artifact cleanup and real provider results remain later tasks.

## Next task

Review T07 and its actual draft checks. After user merge and a separate assignment,
implement **T11 only** to finish the local demonstration: platform access requests,
owner/admin decisions, effective-access revocation feedback and archive with
unresolved-work rejection. T11 may precede T08 under the development plan. Inspect
Git status, verify merged prerequisites on updated main and create its own branch.
Do not start T08–T10, publish repositories or activate providers automatically.

## Files to read first

- AGENTS.md; mdfiles/README.md; T07/T11 in development-plan.md; next-agent.md.
- mdfiles/domain-contracts.md, api-contracts.md, architecture.md; ADR-019 in decisions.md.
- backend/models/job_run.py, job_run_schemas.py; migration 010_simulated_job_runs.py.
- backend/services/job_run_service.py, queue_service.py, operation_service.py;
  backend/worker.py; backend/api/endpoints/job_runs.py.
- frontend/src/pages/job-runs.tsx, application-dashboard.tsx, applications.tsx.
- tests/unit/test_job_runs.py; tests/integration/test_job_runs.py, test_migrations.py;
  frontend/e2e/workflows.spec.ts; tests/browser_server.py; .github/workflows/ci.yml.
- For T11: existing policy/application/environment services, role/membership API,
  and application lifecycle/operation reservation models. Reuse current policy.

## Suggested agent prompt

Read AGENTS.md and mdfiles/README.md, next-agent.md and the T11 contracts. Inspect
Git status and preserve unrelated work, the abandoned T05 branch/stash and its old
008_bundle_generation database. Verify T07 is reviewed and merged on updated main
before implementing separately assigned T11 on its own branch. Build only platform
access-request/decision, effective revocation feedback and archive workflow with
React UI, transaction/audit/permission checks and unresolved-operation protection.
Use isolated test data, record actual verification and update the handoff. Leave
merging to the user; do not activate external providers or convert the old database.
