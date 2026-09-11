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
root `.env` to override it. Container Compose sets the internal frontend URL to
`http://backend:8000`.

## Containers

Backend and frontend images build from the locked workspace with uv (pinned to
`0.12.11`, matching CI): a builder stage runs `uv sync --locked --package
<backend|frontend> --no-dev`, and the runtime stage copies only that resulting
virtual environment plus the member's source — no `.env`, credentials, local
`data/`, or host `.venv` are copied in.

```bash
docker compose build
docker compose up
```

`DATABASE_URL` (from `.env`) decides which PostgreSQL the containerized backend
uses:

- **devstack, from the host** (`uv run` directly, no Docker):
  `postgresql://.../data_app_control_plane` with `localhost`.
- **devstack, from Docker Compose**: use `host.docker.internal` instead of
  `localhost`; `docker-compose.yaml` maps that hostname to the host gateway.
- **bundled, self-contained database** (no devstack dependency): start it
  explicitly with `docker compose --profile local-db up`, and point
  `DATABASE_URL` at `db` (e.g. `postgresql://...@db:5432/...`). It is disabled
  by default and never a mandatory dependency of `backend`. Its host port
  defaults to `5433` (`POSTGRES_HOST_PORT`) to avoid colliding with devstack's
  PostgreSQL on `5432`.

See `.env.example` for the exact `DATABASE_URL` value in each case. Frontend's
container `API_URL` is fixed to `http://backend:8000` by Compose; running the
frontend image standalone (outside Compose) requires setting `API_URL` to
wherever the backend is actually reachable from that container.

Image builds and a live `docker compose up` smoke check have not been run as
part of this change — no Docker daemon was available in the environment that
implemented it. Compose/Dockerfile syntax was reviewed manually, not validated
with `docker compose config`.

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
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
```

Unit tests (`tests/unit`, the default `testpaths`) block network calls. Startup and
migration-rendering tests use an isolated process with controlled configuration; no
running database or provider is required. UI tests use Streamlit's test runner and
mocked HTTP responses. Mypy is initially scoped to the new settings and API
assembly; unrelated legacy modules are not yet under strict checking.

Isolated PostgreSQL migration integration tests (`tests/integration`, marked
`integration`) are not part of the default `testpaths` and need a dedicated,
disposable pgvector-capable database:

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/disposable_test_db \
  uv run --locked pytest tests/integration -q
```

Each test runs inside its own uniquely named schema in that database and drops it
afterward; never point `TEST_DATABASE_URL` at a shared or primary database. Unset,
these tests are skipped with a visible reason rather than failing. GitHub Actions
CI (`.github/workflows/ci.yml`) runs them against a throwaway `pgvector/pgvector`
service container.

Historical migration files and database contents are preserved. Removed feature
metadata lives in `backend/alembic/legacy_models.py` and is loaded only by Alembic,
so future autogeneration does not propose dropping retained tables. Offline SQL
rendering is not proof of a successful migration on a live database; T01b adds that
check. Legacy auth/example HTTP scripts are kept under `tests/manual/` and are not
collected by pytest; the example endpoint is not mounted in the platform API.
