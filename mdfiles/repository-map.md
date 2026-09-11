# Repository map

Inspected 2026-09-11. Paths below are current unless labelled proposed. Recheck
affected files before editing; avoid a full repository crawl for each task.

## Current implementation

| Path | Responsibility / relevant limitation |
|---|---|
| `backend/main.py` | FastAPI assembly; imports every legacy router; health is process-only and metrics are placeholders |
| `backend/core/config.py` | Cached Pydantic settings; requires LLM settings and selected provider key |
| `backend/core/database.py` | Synchronous engine/session/base; settings constructed on import |
| `backend/core/logging.py` | Basic Python logging, no structured audit/correlation |
| `backend/models/database.py` | User, dataset, ML model, pipeline, chat, vector, and background-job tables |
| `backend/models/schemas.py` | All legacy Pydantic API schemas in one file |
| `backend/api/endpoints/auth.py` | Register/login/current-user; current-user dependency lives in router |
| `backend/services/auth_service.py` | bcrypt/JWT helpers, user queries; token subject is email |
| `backend/services/job_service.py` | Persists status but accepts in-memory callable; commits internally |
| `backend/api/endpoints/rag.py` | Submits legacy work with FastAPI `BackgroundTasks` |
| `backend/services/{chat,data,rag,llm}_service.py` | Legacy data-science features; not platform domain services |
| `backend/alembic/env.py` | Imports settings and shared model metadata |
| `backend/alembic/versions/001_initial.py` … `004_add_background_jobs.py` | Existing migration chain; preserve it |
| `frontend/app.py` | Single Streamlit file; hardcoded `http://backend:8000/`, auth/chat/API tester |
| `pyproject.toml` | uv workspace containing backend and frontend |
| `backend/pyproject.toml`, `frontend/pyproject.toml`, `uv.lock` | Local dependencies/lock; legacy AI dependencies remain |
| `backend/Dockerfile`, `frontend/Dockerfile` | pip installs from separate requirements files; flattened container imports |
| `docker-compose.yaml` | Bundled pgvector database; backend DB name hardcoded; no worker |
| `tests/test_auth.py`, `tests/test_request.py` | Live HTTP scripts with import-time side effects |
| `tests/test_rag_service.py` | Live server/provider tests; pytest-style functions lack a supplied `headers` fixture |
| `README.md` | Legacy template guide; retain relevant legacy notes when replacing the main introduction |

## Reuse and migration strategy

Reuse FastAPI, Pydantic, synchronous SQLAlchemy, Alembic, PostgreSQL, Streamlit,
and uv. Keep old tables/migrations intact; disable legacy routers and LLM startup
in the default platform profile. Do not delete uploaded files or rewrite old
migrations as a shortcut. Existing vector migrations may still require pgvector;
verify the test/dev database supports it until a dedicated migration addresses it.

Introduce new platform modules alongside legacy files. Do not repurpose legacy
`Pipeline` as an application or legacy `BackgroundJob` as the durable queue.
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

During documentation preparation, `.gitignore` was independently changed to include
`uv.lock` and `.mdfiles`. That edit was left untouched. T01 must check lockfile
tracking: a clean CI checkout needs the agreed lockfile available. `.mdfiles` is a
different path from the `mdfiles/` documentation directory used here.
