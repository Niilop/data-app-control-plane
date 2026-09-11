# Repository map

Inspected 2026-09-11. Paths below are current unless labelled proposed. Recheck
affected files before editing; avoid a full repository crawl for each task.

## Current implementation

| Path | Responsibility / relevant limitation |
|---|---|
| `backend/main.py` | FastAPI assembly; auth/system and T02/T03 registry and T04 operation routes, request IDs and safe error handlers; no AI routes |
| `backend/core/config.py` | Cached settings; explicit simulated executor, local-only profile gate, DB/auth settings, sanitized validation errors and SQL debug off |
| `backend/core/database.py` | Synchronous engine/session and typed DeclarativeBase; settings constructed on import |
| `backend/core/logging.py` | Basic Python logging, no structured audit/correlation |
| `backend/models/database.py` | User (T02 active/admin flags), dataset, and dormant pipeline tables; historical AI models moved to Alembic |
| `backend/models/schemas.py` | All legacy Pydantic API schemas in one file |
| `backend/api/endpoints/auth.py` | Compatible register/login/profile; central actor dependency checks current active status |
| `backend/services/auth_service.py` | bcrypt/JWT helpers and audited public account creation; token subject is email; inactive login denied |
| `backend/alembic/legacy_models.py` | Migration-only metadata for removed AI/model/job tables; prevents destructive autogeneration |
| Former `chat`, `rag`, `llm`, `jobs` routers/services | Removed in T01a, including RAG-only background execution |
| `backend/services/data_service.py` | Dormant CSV support; not a platform domain service |
| `backend/alembic/env.py` | Imports runtime plus historical metadata; local package marker removed to avoid shadowing installed Alembic; T01b: escapes `%` in `sqlalchemy.url` for `configparser`, and caches the `legacy_models` load in `sys.modules` so re-running migrations in one process doesn't re-register `Base.metadata` tables |
| `backend/alembic/versions/001_initial.py` … `004_add_background_jobs.py` | Existing migration chain; preserve it |
| `frontend/src/App.tsx`, `src/state.tsx`, `src/api.ts` | React routing, local account/session state, abortable API reads, safe error feedback and in-memory command keys |
| `pyproject.toml` | uv workspace containing the backend and Python verification tools |
| `backend/pyproject.toml`, `uv.lock` | Locked Python runtime and checks; Streamlit workspace/dependencies retired in T04a |
| `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf` | uv-locked API/worker; npm-locked React build and nginx static assets with same-origin API proxy |
| `.dockerignore` | T01b: root ignore file for the `context: .` Compose builds (`requirements.txt` files remain but are unused by the Dockerfiles) |
| `docker-compose.yaml` | T01b: bundled `db` service moved behind the opt-in `local-db` Compose profile with a configurable host port (default 5433); `backend` gets `host.docker.internal` for devstack access and a non-blocking `depends_on: db` |
| `tests/manual/auth_smoke.py`, `tests/manual/request_smoke.py` | Historical manual HTTP examples; not pytest tests |
| `tests/unit/`, `tests/conftest.py` | Offline settings/startup/migration-rendering and platform API tests; shared SQLite registry fixture and network guard (integration tests exempt) |
| `tests/integration/test_migrations.py` | Isolated PostgreSQL+pgvector migration, T02 schema parity/legacy user preservation, API rollback/constraints and concurrent version-update tests; gated on `TEST_DATABASE_URL` |
| `.github/workflows/ci.yml` | Python lint/format/type/offline tests, isolated PostgreSQL tests, and locked React build/browser checks |
| `README.md` | Current local startup and focused verification commands |
| `.github/pull_request_template.md` | Same-PR handoff, verification, and related documentation checklist |
| `.github/workflows/agent-handoff.yml` | Lightweight PR handoff validation, separate from platform CI |
| `scripts/check_agent_handoff.py` | Standard-library checker for merge-base changes, handoff structure, and substantive update |
| `tests/unit/test_agent_handoff.py` | Disposable Git histories exercise enforcement and exemptions |

### T02 implementation modules

| Path | Responsibility |
|---|---|
| `backend/models/platform.py`, `platform_schemas.py` | UUID teams/memberships/applications/roles/audit ORM; bounded strict API schemas and source/path validation |
| `backend/alembic/versions/005_owned_applications.py` | Add registry and safe active/admin user defaults; versions 001–004 unchanged |
| `backend/api/dependencies.py`, `platform_errors.py` | Database-current actor/admin dependencies; request UUIDs and sanitized envelopes |
| `backend/api/endpoints/applications.py`, `teams.py` | T02 registry, ownership/roles, team/membership and application/admin audit routes |
| `backend/services/application_service.py` | Command transaction ownership, atomic audit, version-predicate metadata updates |
| `backend/services/policy_service.py`, `audit_service.py`, `pagination.py` | Central role/visibility policy, flush-only audit helper, scoped keyset navigation |
| `backend/bootstrap.py` | Explicit prompted local account/admin creation; refuses overwrite; audited |
| `frontend/src/pages/applications.tsx` | Application list/register/detail/edit, snapshot versions, ownership and direct/team role controls |
| `tests/unit/test_registry.py`, `frontend/e2e/workflows.spec.ts` | Offline registry policy/transactions and real-browser API workflows |

### T03 implementation modules

| Path | Responsibility |
|---|---|
| `backend/models/platform.py`, `backend/models/environment_schemas.py` | Environment/binding ORM and strict local simulation/target/config schemas |
| `backend/alembic/versions/006_environment_bindings.py` | Add versioned environments and unique application bindings; 001–005 unchanged |
| `backend/services/environment_service.py` | Admin policy, filtered reads, environment row locks, binding version invalidation and atomic audit |
| `backend/api/endpoints/environments.py` | Environment and application-binding create/list/detail/update routes |
| `backend/seed_sandbox.py` | Explicit local admin seed; repeatable, audited, no overwrites or external calls |
| `frontend/src/pages/administration.tsx`, `src/ReferenceSelect.tsx`, `src/components.tsx` | Teams/members, environments/bindings, audit/profile, paginated selectors and shared accessible forms |
| `tests/unit/test_environments.py`, `frontend/e2e/workflows.spec.ts` | Offline target/config/policy/rollback and browser environment/binding/version workflows |
| `tests/integration/test_environment_bindings.py` | Upgrade preservation, unique/FK checks, rollback and concurrent environment/binding writes on PostgreSQL |

## Reuse and migration strategy

Reuse FastAPI, Pydantic, synchronous SQLAlchemy, Alembic, PostgreSQL and uv.
React + TypeScript + Vite replaces Streamlit in T04a after browser parity passed
(ADR-015/016). New feature screens belong in React. Keep old tables/migrations intact; remove AI runtime
features per the user's clarification; keep dormant CSV/example
modules unmounted for now. Do not delete uploaded files or rewrite old
migrations as a shortcut. Existing vector migrations may still require pgvector;
verify the test/dev database supports it until a dedicated migration addresses it.

Introduce new platform modules alongside legacy files. Do not repurpose legacy
`Pipeline` as an application or historical `BackgroundJob` as the durable queue.
Keep the existing import layout initially; a package-wide rename is outside T01.

## Proposed locations (create only as tasks need them)

| Path | Planned content |
|---|---|
| `backend/api/endpoints/revisions.py`, `access.py` | Workflow endpoints |
| `backend/services/deployment_service.py`, `access_service.py` | Workflow logic |
| `backend/workers/` | Split handlers here when future tasks need them |
| `backend/integrations/` | Only implemented simulation, artifact, GitHub, Databricks adapters |
| `templates/python-batch/` | Versioned generated-project assets and tests |
| `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/e2e/` | Isolated test suites |
| `scripts/` | Explicit seed/demo/check helpers as needed |
| `.github/workflows/` | This platform's own CI, distinct from generated application CI |

Keep this table aligned with the actual implementation after every completed task.
Do not create empty architectural scaffolding for all proposed paths upfront.

`uv.lock`, `AGENTS.md`, and `mdfiles/` are deliberately tracked. The user clarified
that agent instructions should remain in source control; the context handoff on
main resolves the earlier local-only instruction and ignore-file uncertainty.

### T04 implementation modules

| Path | Responsibility |
|---|---|
| `backend/models/operations.py`, `operation_schemas.py` | Durable operation/attempt/reservation/command/probe/worker ORM, closed input and safe views |
| `backend/alembic/versions/007_durable_operations.py` | Add queue tables; preserve migration history and existing registry |
| `backend/services/operation_service.py` | Operator commands, transactional probe submission/audit, idempotency and reservations |
| `backend/services/queue_service.py` | PostgreSQL atomic claims, leases, heartbeat, fencing, backoff and related-result writes |
| `backend/worker.py`, `backend/queue_probe.py` | Separate polling process, fixed deterministic simulated handler and local success-probe CLI |
| `backend/api/endpoints/operations.py`, `backend/main.py` | Authorized operation/history/recovery and admin telemetry; liveness/readiness |
| `frontend/src/pages/operations.tsx`, `src/api.ts` | Operation/attempt history, observation freshness and keyed recovery commands |
| `tests/unit/test_operations.py`, `tests/integration/test_operations.py` | Offline API/state/failure cases; real PostgreSQL process contention/restart/heartbeat, fencing and rollback |

### T04a frontend and browser sessions

| Path | Responsibility |
|---|---|
| `frontend/package.json`, `package-lock.json`, `.node-version`, `.npmrc` | Exact direct dependencies, lockfile, Node/npm version and local scripts |
| `frontend/vite.config.ts`, `tsconfig.json`, `eslint.config.js` | Build/types/lint; no env-file discovery; local same-origin API proxy |
| `frontend/src/styles.css` | Clean light design, responsive navigation/tables/forms, visible keyboard focus |
| `backend/api/browser_session.py`, `backend/api/endpoints/auth.py` | HTTP-only cookie login/logout and custom-header/origin write protection |
| `backend/api/endpoints/applications.py`, `backend/models/platform_schemas.py` | Current application capabilities response; mutations retain authoritative policy |
| `tests/unit/test_browser_session.py` | Cookie/bearer compatibility, CSRF, expiry/inactive identity and current capabilities |
| `frontend/playwright.config.ts`, `frontend/e2e/workflows.spec.ts` | Real Chromium account/registry/admin/recovery and mobile/keyboard workflows |
| `tests/browser_server.py` | Disposable SQLite API/worker fixtures; no developer database or fixture endpoints |
| `tests/Dockerfile.browser`, `tests/Dockerfile.browser.dockerignore` | Isolated Chromium/Node/uv verification image with restricted build context |
| `tests/compose.browser.yaml`, `frontend/e2e/nginx-smoke.mjs` | Disposable production nginx/API browser smoke; no application DB volume or credentials |
