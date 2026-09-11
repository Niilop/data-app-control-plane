# Agent handoff

This describes implemented code, not merge status. Inspect Git status, preserve
unrelated changes, verify prerequisites on updated main, and read AGENTS.md before
starting the next bounded task. Do not assume this implementation PR is merged.

## Implemented state

T01 is merged via PR #5 at `07e90c5`. At T02 start, GitHub CLI confirmed that same
commit was current main and this task branch contained it. The existing handoff
reconciliation commit was retained. **T02 — Register an owned application is
implemented and awaiting PR review/merge.** No T03/environment/worker/provider
features were added. AI/chat/RAG/LLM/inference remain removed.

- Migration `005_owned_applications` extends users with `is_active=true` and
  `is_platform_admin=false`, preserving existing users and migrations 001–004.
  New UUID/UTC tables: teams, unique memberships, applications, direct/team role
  assignments, and audit. Foreign keys retain references without delete cascades.
  New models use SQLAlchemy's typed declarative base; sessions remain synchronous.
- `/auth/register`, form `/auth/login` (email or username), and `/auth/me` remain.
  Public registration rejects unknown/privilege fields and creates nonadmins.
  Identity is resolved from the database on every authenticated request; inactive
  users cannot log in or reuse a token. No external identity integration or
  account-deactivation management endpoint exists yet.
- `backend/bootstrap.py` creates explicit new local accounts, prompting twice for
  passwords; `--admin` is opt-in. It refuses to overwrite/promote existing users
  and records admin intent with actor kind `local_bootstrap`. No default accounts,
  passwords, credentials or external identity changes are activated automatically.
- T02 API covers teams/memberships, application registration/list/detail,
  versioned metadata/ownership updates, roles/revocation and audit. Supporting
  reads include team members, application roles and admin-wide audit history.
  All lists paginate by `(created_at,id)` after current permission filtering;
  validated base64 cursors are scoped to endpoint and actor, not frozen snapshots.
- Any registrant, including admin, must belong to the owning team. Creator gets
  direct developer + viewer. Accountable owner/data owner must be active users;
  both can read, only owner/admin can manage ownership/roles. Owning-team
  membership alone gives no read access. Team/direct roles union; revocation
  affects subsequent requests. Metadata/source edits require developer even for
  admin; mixed ownership/metadata patches require both permissions.
- Registration validates only HTTPS github.com owner/repository references and
  conservative relative bundle paths. Optional `.git` suffix normalizes away.
  No network verification occurs: `repository_verified_at=null`, visibly
  unverified in UI. No platform role grants GitHub/Databricks/data permissions.
- Application services own commit/rollback; audit helpers flush only. Creation,
  initial roles and success audit are atomic. Metadata updates use a database
  version predicate and increment; stale edits return 409 without a success event.
  UUID request IDs correlate API headers/error envelopes and mutation audit.
  Validation/server errors omit submitted values and raw database diagnostics.
- Streamlit uses authenticated HTTP/timeouts for paginated registration,
  detail/metadata/ownership, roles/history, team membership and admin audit.
  Account IDs are visible on profiles and entered explicitly for accountability.
  Forms retain the displayed version across submit reruns to reject stale edits.
- CI now checks all changed/new T02 modules with Ruff, and mypy covers 18 platform
  files. No dependency added; `uv.lock` unchanged. Tests include offline SQLite
  API behavior, Streamlit workflows through the in-process API, and isolated
  PostgreSQL migration/API/concurrency checks.

## Verification performed

Actually run locally:

- `uv sync --locked --all-packages --group dev --offline`: passed using existing
  locked packages (uv 0.12.11, Python 3.11.16).
- `uv run --locked pytest -q`: **67 passed**. Includes 27 registry API cases and
  3 Streamlit workflows, plus the existing 37 tests. Offline network guard stayed
  enabled. TestClient stalls within this execution sandbox; tests passed outside
  that restriction. Coverage includes permission-filtered lists/detail/audit,
  creator roles, invalid references/paths/privilege fields, optimistic updates,
  role/team revocation, inactive tokens, bootstrap/login and injected rollback.
- `uv run --locked mypy`: passed, 18 source files.
- Ruff lint and formatting passed over the current explicit scope in root README
  and `.github/workflows/ci.yml` (all changed/new runtime files, new migration,
  frontend and tests; historical migration versions left untouched).
- `uv run --locked pytest tests/integration -q -rs`: **6 skipped** locally with
  the documented reason because `TEST_DATABASE_URL` is unset. No local PostgreSQL
  migration, locking or constraint verification is claimed from these skips.
- `docker version`: launcher reports Docker unavailable in this WSL distro and
  asks for WSL integration. No image builds or live container checks were run.

T01b's prior hosted evidence remains PR #5, Platform CI run 34608464924 at
`a50795c`: three migration tests passed against pgvector/PostgreSQL. That validates
T01b only. T02 hosted CI results must be checked for the actual PR revision; they
are not yet recorded here. Handoff mechanical checks do not prove these claims.

## Remaining work and limitations

- Review this PR, including identity/policy changes, and confirm hosted T02 CI
  before merge. Do not infer merge or PostgreSQL success from this file.
- T02's six PostgreSQL tests include fresh-chain/old-head upgrades, legacy user
  preservation/default flags, new ORM/schema parity, direct database constraints,
  API/audit rollback and simultaneous versioned updates. Local SQLite tests are
  not evidence for PostgreSQL semantics.
- Docker builds, `docker compose up`/health and real devstack integration remain
  unverified. No devstack checkout or configured disposable test DB was available.
- Bootstrap is direct local DB administration, not a production identity system.
  No users were bootstrapped into a real database during this implementation.
- Repository verification is deferred to T08. Environment bindings, operations,
  deployments, approvals, access requests and archive endpoints remain later tasks.
  Audit has no write/delete API but is not tamper-proof against database admins.
- No cloud resources, external permissions, provider credentials or paid workloads
  were used. Legacy dependency deprecation warnings remain; no broad upgrade made.

## Next task

Verify T02 is merged into updated main and inspect current checks. Then implement
**T03 — Register a sandbox environment binding** only, on its own task branch.
T03 adds admin environment/binding models, migration, API/UI, explicit simulated
sandbox configuration and self-approval policy, versioned safe binding config,
and startup rejection of unsupported organization/profile combinations. No
workspace creation, Terraform, connectivity validation or deployment.

If T02 is not merged, finish its review/corrections first. Preserve unrelated
changes and create the task branch only after inspecting Git status/prerequisites.
Do not carry temporary checkout state from this handoff into the next task.

## Files to read first

| Purpose | Files |
|---|---|
| Entry/task | `AGENTS.md`, `mdfiles/README.md`, T03 in `mdfiles/development-plan.md` |
| Binding/profile contracts | `mdfiles/architecture.md`, `mdfiles/domain-contracts.md`, T03 rows in `mdfiles/api-contracts.md` |
| Registry model/migration patterns | `backend/models/platform.py`, `platform_schemas.py`, `backend/alembic/versions/005_owned_applications.py`, `backend/alembic/env.py` |
| Authorization/transactions | `backend/api/dependencies.py`, `backend/services/policy_service.py`, `application_service.py`, `audit_service.py`, `pagination.py` |
| API/config/error assembly | `backend/main.py`, `backend/core/config.py`, `backend/api/platform_errors.py`, `backend/api/endpoints/applications.py`, `teams.py` |
| UI | `frontend/app.py`, `api_client.py`, `registry.py` |
| Checks | `tests/conftest.py`, `tests/unit/test_registry.py`, `test_registry_ui.py`, `tests/integration/test_migrations.py`, root README, CI workflow |

Do not read `.env` into tool output. Local PostgreSQL/Redis, when available, belong
to `~/code/devstack`; use isolated app/test databases and do not change shared
configuration or other databases. Redis is not needed by this platform.

## Suggested agent prompt

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Inspect Git status
> and verify T02 is merged into updated main, including current CI evidence.
> Implement T03 only on its own branch, preserving unrelated changes. Explain
> the plan, run the acceptance checks, update this handoff and affected docs in
> the same PR, and open a draft PR against main. Do not merge, start T04, create
> cloud resources or deploy infrastructure. Keep simulation explicit. Docker
> builds/startup remain unverified unless newer evidence establishes otherwise.
