# Repository map

Inspected 2026-09-11. Paths below are current unless labelled proposed. Recheck
affected files before editing; avoid a full repository crawl for each task.

## Current implementation

| Path | Responsibility / relevant limitation |
|---|---|
| `backend/main.py` | FastAPI assembly; auth/system and T02/T03 registry routes, request IDs and safe error handlers; no AI routes |
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
| `frontend/app.py` | Development account/status and T02/T03 registry UI entry point; API_URL configurable; no AI UI |
| `pyproject.toml` | uv workspace containing backend and frontend |
| `backend/pyproject.toml`, `frontend/pyproject.toml`, `uv.lock` | Tracked lock and dependencies; AI providers/LangChain removed, dev tooling added |
| `backend/Dockerfile`, `frontend/Dockerfile` | T01b: multi-stage, uv-locked (`uv sync --locked --package <name>`) builds pinned to `ghcr.io/astral-sh/uv:0.12.11`; venv at `/opt/venv`, not under the Compose dev bind mount |
| `.dockerignore` | T01b: root ignore file for the `context: .` Compose builds (`requirements.txt` files remain but are unused by the Dockerfiles) |
| `docker-compose.yaml` | T01b: bundled `db` service moved behind the opt-in `local-db` Compose profile with a configurable host port (default 5433); `backend` gets `host.docker.internal` for devstack access and a non-blocking `depends_on: db` |
| `tests/manual/auth_smoke.py`, `tests/manual/request_smoke.py` | Historical manual HTTP examples; not pytest tests |
| `tests/unit/`, `tests/conftest.py` | Offline settings/startup/migration-rendering and T02 API/UI tests; shared SQLite registry fixture and network guard (integration tests exempt) |
| `tests/integration/test_migrations.py` | Isolated PostgreSQL+pgvector migration, T02 schema parity/legacy user preservation, API rollback/constraints and concurrent version-update tests; gated on `TEST_DATABASE_URL` |
| `.github/workflows/ci.yml` | T01b: platform CI — locked lint/format/type/offline-test job, plus an isolated migration job using a `pgvector/pgvector` service container |
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
| `frontend/api_client.py`, `registry.py` | Authenticated HTTP/timeouts; application registration/detail/edit/history and minimal team/role controls |
| `tests/unit/test_registry.py`, `test_registry_ui.py` | Offline API authorization/validation/atomicity and Streamlit-to-API workflows |

### T03 implementation modules

| Path | Responsibility |
|---|---|
| `backend/models/platform.py`, `backend/models/environment_schemas.py` | Environment/binding ORM and strict local simulation/target/config schemas |
| `backend/alembic/versions/006_environment_bindings.py` | Add versioned environments and unique application bindings; 001–005 unchanged |
| `backend/services/environment_service.py` | Admin policy, filtered reads, environment row locks, binding version invalidation and atomic audit |
| `backend/api/endpoints/environments.py` | Environment and application-binding create/list/detail/update routes |
| `backend/seed_sandbox.py` | Explicit local admin seed; repeatable, audited, no overwrites or external calls |
| `frontend/environment_ui.py`, `frontend/registry_widgets.py` | Environment/binding screens and shared pagination/feedback extracted from T02 registry UI |
| `tests/unit/test_environments.py`, `tests/unit/test_registry_ui.py` | Offline target/config/policy/rollback and real in-process API/UI workflows |
| `tests/integration/test_environment_bindings.py` | Upgrade preservation, unique/FK checks, rollback and concurrent environment/binding writes on PostgreSQL |

## Reuse and migration strategy

Reuse FastAPI, Pydantic, synchronous SQLAlchemy, Alembic, PostgreSQL, Streamlit,
and uv. Keep old tables/migrations intact; remove AI runtime features per the user's clarification; keep dormant CSV/example
modules unmounted for now. Do not delete uploaded files or rewrite old
migrations as a shortcut. Existing vector migrations may still require pgvector;
verify the test/dev database supports it until a dedicated migration addresses it.

Introduce new platform modules alongside legacy files. Do not repurpose legacy
`Pipeline` as an application or historical `BackgroundJob` as the durable queue.
Keep the existing import layout initially; a package-wide rename is outside T01.

## Proposed locations (create only as tasks need them)

| Path | Planned content |
|---|---|
| `backend/api/endpoints/revisions.py`, `operations.py`, `access.py` | Workflow endpoints |
| `backend/services/operation_service.py`, `deployment_service.py`, `access_service.py` | Workflow logic |
| `backend/worker.py` | Independently runnable worker entry point |
| `backend/workers/` | Claims, handlers, retry/reconciliation code |
| `backend/integrations/` | Only implemented simulation, artifact, GitHub, Databricks adapters |
| `templates/python-batch/` | Versioned generated-project assets and tests |
| `frontend/pages/` | Split platform screens here as later tasks need them |
| `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/e2e/` | Isolated test suites |
| `scripts/` | Explicit seed/demo/check helpers as needed |
| `.github/workflows/` | This platform's own CI, distinct from generated application CI |

Keep this table aligned with the actual implementation after every completed task.
Do not create empty architectural scaffolding for all proposed paths upfront.

`uv.lock`, `AGENTS.md`, and `mdfiles/` are deliberately tracked. The user clarified
that agent instructions should remain in source control; the context handoff on
main resolves the earlier local-only instruction and ignore-file uncertainty.
