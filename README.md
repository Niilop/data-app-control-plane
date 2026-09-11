# Data Application Control Plane

A local-first, self-service platform for managing Databricks data applications
backed by GitHub repositories. See [the development plan](mdfiles/README.md) for
scope, architecture, contracts, and bounded agent tasks.

The first implementation block provides FastAPI startup, development login, a
Streamlit account/status page, and an offline test baseline. Application registry,
workers, GitHub Actions integration, and Databricks deployment are planned work.
The old AI chat, RAG, LLM, and model-inference features have been removed.

## Local setup

Python 3.11 is selected by `.python-version`. Use uv from the repository root:

```bash
uv sync --locked --all-packages --group dev
cp .env.example .env
```

Set `DATABASE_URL` to a dedicated development PostgreSQL database and replace
`SECRET_KEY` with a random local secret. No AI API keys are used. Do not commit
`.env`. The existing migration chain still requires PostgreSQL with pgvector.
Use the existing devstack when available; do not point migrations at another
application's database.

From `backend/`:

```bash
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --reload
```

From `frontend/` in another terminal:

```bash
uv run --locked streamlit run app.py
```

The UI defaults to `http://localhost:8000`; set `API_URL` in the environment or
root `.env` to override it. Existing Compose configuration sets the internal
frontend URL to `http://backend:8000`. Container dependency locking, devstack
integration, and live migration verification are the next block, T01b; the old
Compose database configuration is not yet the recommended startup path.

## Available endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Application identity |
| GET | `/health` | Process liveness only, not database readiness |
| POST | `/auth/register` | Create a development account |
| POST | `/auth/login` | Email/username and password as form data |
| GET | `/auth/me` | Current user; requires bearer token |
| GET | `/docs` | OpenAPI UI |

AI routes and placeholder metrics are absent. CSV/example modules remain dormant
and are not mounted by the platform API. Authorization roles arrive in T02.

## Verification

```bash
uv run --locked pytest -q
uv run --locked mypy
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit
```

Unit tests block network calls. Startup and migration-rendering tests use an
isolated process with controlled configuration; no running database or provider is
required. UI tests use Streamlit's test runner and mocked HTTP responses. Mypy is
initially scoped to the new settings and API assembly; unrelated legacy modules
are not yet under strict checking.

Historical migration files and database contents are preserved. Removed feature
metadata lives in `backend/alembic/legacy_models.py` and is loaded only by Alembic,
so future autogeneration does not propose dropping retained tables. Offline SQL
rendering is not proof of a successful migration on a live database; T01b adds that
check. Legacy auth/example HTTP scripts are kept under `tests/manual/` and are not
collected by pytest; the example endpoint is not mounted in the platform API.
