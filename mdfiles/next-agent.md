# Agent handoff

Inspect Git status, preserve unrelated work, verify prerequisites on updated main,
and read AGENTS.md before creating or continuing a task branch. This handoff does
not claim the current T05 draft is merged.

## Implemented state

T01–T04a are merged. PR #10 was verified merged at
`6503ec152a7bcfbb3310e45c08f5fab78dea27d6`. This fresh T05 implementation starts
from that baseline. Earlier T05 branch/stash work is preserved separately.
AI/chat/RAG/LLM/inference remain removed. Accounts, registry and migration history
001–007 are retained.

T05 provides the `python-batch:1.0.0` template with synthetic batch code, stdlib
tests and its own dependency-free uv lock. Canonical stored ZIP entries have fixed
metadata, sorted names and a manifest binding parameters/config/template digests.
Inputs are closed; no arbitrary paths, source, secrets or external commands.

The API submits `generate_bundle` and `validate_offline` to the existing durable
worker with `execution_mode=offline`. Developer permission is required at request,
execution and completion; recovery retains operator permission (retry also requires
developer). Existing binding reservations, leases, fencing and command keys apply.
Completion associates artifacts/reports only inside the fenced audited transaction.
A lost worker may leave unreferenced immutable bytes; replay is safe for these local
handlers. Probe semantics and simulated labels remain separate.

Local artifact writes publish atomically with fsync and SHA-256 verification;
reads reject missing/corrupt/symlink/nonregular/oversized content and require an
associated visible application. API and worker share `ARTIFACT_DIR`; Compose mounts
`./data` into both. API responses contain no storage paths or queue payloads.

Revision capture is an explicit synchronous command using a completed generation
and unchanged binding version. Source/config/template/policy snapshots are immutable;
PostgreSQL triggers protect artifacts/revisions/reports/template content against
SQL mutation. Validation checks exact approved archive content and static Python/
TOML syntax without executing source. Reports always say offline, never workspace.
React's Preparation tab covers generation/download/capture/report workflows and
links operation IDs to the existing Operations tab for progress/recovery.

## Verification performed

Local checks on 2026-09-14:

- `uv run --locked pytest -q`: **147 passed** (22 preparation cases), with the
  offline network guard. After ending worker read transactions before filesystem
  work, all 22 preparation cases passed again; after preserving probe assertions, all
  39 queue/preparation cases passed. Mypy passed for 34 modules; CI-scoped Ruff
  lint/format passed across 58 files.
- `uv run --locked pytest tests/integration -q`: **17 passed**, no skips, against
  a new disposable pgvector/pg16 container on loopback port 55439. Checks include
  legacy account/data and migration/ORM parity, SQL immutability, concurrent
  idempotent submission, two-binding artifact completion, queue fencing/recovery.
- Generated project: fresh temporary project/cache, locked offline uv installation
  and stdlib tests passed (2 tests). No global package installation was needed.
- Frontend lint, Prettier, TypeScript and Vite build passed. Docker test image
  installed locked dependencies with npm ci. **10 Chromium workflows passed**
  against a disposable real API and worker, including generation/download/capture/
  offline validation. Desktop/390px screenshots were inspected. The preparation workflow passed
  again after the spacing/control styling follow-up.
- Production frontend image built. Isolated Compose nginx smoke passed routing,
  CSP, cookie login/reload, authenticated write, worker readiness and logout.
- Native Chromium initially could not launch because WSL lacks libnspr4.so.
  After the user started Docker Desktop, container checks succeeded. The existing
  application DB, accounts, Compose services and old T05 migration were untouched.
- Current hosted CI is not yet claimed passed; inspect the draft's latest checks.
  No provider connectivity, repository publication or deployment was performed.

## Remaining work and limitations

- Complete/review current CI and this draft; T05 is not merged. Review schema and
  workflow permissions before user merge. No T06 implementation exists.
- The abandoned branch reportedly migrated the local app database to
  `008_bundle_generation`. This branch uses `008_prepared_revisions` from merged
  007 and does not alter that database. Do not stamp over the old revision, delete
  tables, or run this migration against it. Use a separate database from updated
  main for T05 testing; any conversion of the old database needs an explicit,
  data-preserving migration plan after inspecting its actual state.
- Local storage trusts the configured root and host administrator. Unreferenced
  files can remain after crashes; automatic garbage collection is deferred. Back
  up the DB and shared artifact directory together; no shared/remote store exists.
- Offline validation is static allowlist/integrity validation. It neither executes
  tests in the general worker nor verifies Databricks schema/workspace/compute.
  The generated project is tested separately in a disposable environment. Provider
  identity, compute selection, workflow publication and deployments are deferred.
- Generation/validation keys survive transport retries and dialog reopen within
  the signed-in workspace. Reload clears browser memory; inspect existing history
  before repeating work. Revision creation is synchronous and may create another
  immutable record if deliberately repeated; it has no idempotency-key contract.
- Existing development session limitations remain: logout does not revoke copied
  JWTs. Organization SSO, global token revocation and real providers are later work.

## Next task

Finish T05 review and verify its draft CI. After the user merges T05 and assigns
new work, implement **T06 only**: exact-scope approval and one simulated deployment.
Verify merged prerequisites on updated main, then create a new task branch.
Do not begin T06 simply because T05 code exists on a branch.

## Files to read first

- AGENTS.md; mdfiles/README.md; T05/T06 in development-plan.md; ADR-017 in decisions.md.
- mdfiles/domain-contracts.md, api-contracts.md, integrations.md and architecture.md.
- backend/services/delivery_service.py, template_service.py, queue_service.py,
  operation_service.py and backend/worker.py.
- backend/models/delivery.py, delivery_schemas.py;
  backend/alembic/versions/008_prepared_revisions.py; backend/integrations/artifact_store.py.
- backend/templates/python_batch_v1; scripts/check_generated_project.py;
  frontend/src/pages/preparation.tsx and frontend/e2e/workflows.spec.ts.
- tests/unit/test_delivery.py, tests/integration/test_delivery.py,
  tests/integration/test_migrations.py, tests/browser_server.py and .github/workflows/ci.yml.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md and mdfiles/next-agent.md. Inspect Git status,
preserve unrelated work, verify the T05 draft and current CI against updated main.
Review T05 only, including data preservation, immutable snapshots, digest checks,
authorization, fencing and browser behavior. Do not claim it merged, begin T06,
modify the abandoned-branch database, publish repositories or activate providers.
