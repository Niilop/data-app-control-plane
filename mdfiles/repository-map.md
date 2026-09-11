# Repository map

Inspected 2026-09-11. Paths below are current unless labelled proposed. Recheck
affected files before editing; avoid a full repository crawl for each task.

## Current implementation

| Path | Responsibility / relevant limitation |
|---|---|
| `backend/main.py` | FastAPI assembly; auth/system routes only; AI routes and placeholder metrics removed in T01a |
| `backend/core/config.py` | Cached Pydantic settings; DB/auth settings only; SQL debug off by default; no AI settings |
| `backend/core/database.py` | Synchronous engine/session/base; settings constructed on import |
| `backend/core/logging.py` | Basic Python logging, no structured audit/correlation |
| `backend/models/database.py` | User, dataset, and dormant pipeline tables; historical AI models moved to Alembic |
| `backend/models/schemas.py` | All legacy Pydantic API schemas in one file |
| `backend/api/endpoints/auth.py` | Register/login/current-user; current-user dependency lives in router |
| `backend/services/auth_service.py` | bcrypt/JWT helpers, user queries; token subject is email |
| `backend/alembic/legacy_models.py` | Migration-only metadata for removed AI/model/job tables; prevents destructive autogeneration |
| Former `chat`, `rag`, `llm`, `jobs` routers/services | Removed in T01a, including RAG-only background execution |
| `backend/services/data_service.py` | Dormant CSV support; not a platform domain service |
| `backend/alembic/env.py` | Imports runtime plus historical metadata; local package marker removed to avoid shadowing installed Alembic |
| `backend/alembic/versions/001_initial.py` … `004_add_background_jobs.py` | Existing migration chain; preserve it |
| `frontend/app.py` | Development account/status page; API_URL configurable; no AI UI |
| `pyproject.toml` | uv workspace containing backend and frontend |
| `backend/pyproject.toml`, `frontend/pyproject.toml`, `uv.lock` | Tracked lock and dependencies; AI providers/LangChain removed, dev tooling added |
| `backend/Dockerfile`, `frontend/Dockerfile` | pip installs from separate requirements files; flattened container imports |
| `docker-compose.yaml` | Bundled pgvector database; backend DB name now uses POSTGRES_DB (merged follow-up f1e4381); no worker or optional DB profile yet |
| `tests/manual/auth_smoke.py`, `tests/manual/request_smoke.py` | Historical manual HTTP examples; not pytest tests |
| `tests/unit/`, `tests/conftest.py` | Offline settings/startup/UI/migration-rendering tests and network guards |
| `README.md` | Current local startup and focused verification commands |
| `.github/pull_request_template.md` | Same-PR handoff, verification, and related documentation checklist |
| `.github/workflows/agent-handoff.yml` | Lightweight PR handoff validation; application CI remains T01b |
| `scripts/check_agent_handoff.py` | Standard-library checker for merge-base changes, handoff structure, and substantive update |
| `tests/unit/test_agent_handoff.py` | Disposable Git histories exercise enforcement and exemptions |

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
| `backend/api/dependencies.py` | Current actor, policy dependencies |
| `backend/api/endpoints/applications.py`, `teams.py`, `environments.py` | Registry/admin endpoints |
| `backend/api/endpoints/revisions.py`, `operations.py`, `access.py` | Workflow endpoints |
| `backend/models/platform.py` | Initial new ORM entities, explicitly loaded by Alembic |
| `backend/models/platform_schemas.py` | Typed platform schemas; split further only when useful |
| `backend/services/application_service.py`, `policy_service.py`, `audit_service.py` | Registry/policy/transactional audit |
| `backend/services/operation_service.py`, `deployment_service.py`, `access_service.py` | Workflow logic |
| `backend/worker.py` | Independently runnable worker entry point |
| `backend/workers/` | Claims, handlers, retry/reconciliation code |
| `backend/integrations/` | Only implemented simulation, artifact, GitHub, Databricks adapters |
| `templates/python-batch/` | Versioned generated-project assets and tests |
| `frontend/pages/`, `frontend/api_client.py` | Platform screens and authenticated API access |
| `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/e2e/` | Isolated test suites |
| `scripts/` | Explicit seed/demo/check helpers as needed |
| `.github/workflows/` | This platform's own CI, distinct from generated application CI |

Keep this table aligned with the actual implementation after every completed task.
Do not create empty architectural scaffolding for all proposed paths upfront.

`uv.lock`, `AGENTS.md`, and `mdfiles/` are deliberately tracked. The user clarified
that agent instructions should remain in source control; the context handoff on
main resolves the earlier local-only instruction and ignore-file uncertainty.
