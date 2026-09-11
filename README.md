# Data Application Control Plane

A local-first, self-service platform for managing Databricks data applications
backed by GitHub repositories. See [the development plan](mdfiles/README.md) for
scope, architecture, contracts, and bounded agent tasks.

The platform provides development login, an owned application registry, team and
role administration, transactional audit, and Streamlit registration/detail/history
screens, plus admin-managed simulated environments and application bindings.
A separate durable worker runs explicit simulated probes with operation history
and recovery controls. Bundle generation, GitHub integration and Databricks
deployment remain planned work.
The old AI chat, RAG, LLM, and model-inference features have been removed.

## Local setup

Python 3.11 is selected by `.python-version`. Use uv from the repository root:

```bash
uv sync --locked --all-packages --group dev
cp .env.example .env
```

Set `DATABASE_URL` to a dedicated development PostgreSQL database and replace
`SECRET_KEY` with a random local secret. Set `RUNTIME_PROFILE=local` and explicitly
set `DEPLOYMENT_EXECUTOR=simulated` (also required when upgrading an existing
T02 `.env`). No AI API keys are used. Do not commit
`.env`. The existing migration chain still requires PostgreSQL with pgvector.
Use the existing devstack when available; do not point migrations at another
application's database.

From `backend/`:

```bash
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --reload
```

From `backend/` in a second terminal, start the queue worker:

```bash
uv run --locked python -m worker
```

From `frontend/` in another terminal:

```bash
uv run --locked streamlit run app.py
```

The UI defaults to `http://localhost:8000`; set `API_URL` in the environment or
root `.env` to override it. Container Compose sets the internal frontend URL to
`http://backend:8000`.

## Local accounts and application registration

After migrating the dedicated local database, create an explicit administrator
from `backend/` (password is prompted twice, never supplied as a command argument):

```bash
uv run --locked python -m bootstrap --email your-admin@example.com --username local-admin --admin
```

This administrative command creates only new accounts, refuses to overwrite
existing users, and records `user.bootstrapped` with actor kind `local_bootstrap`.
It has direct database authority and is for local administration. Do not activate
identity changes outside local development before human review. No account or
password is seeded automatically. For separate demo users, repeat with their own
email/username and omit `--admin`, or use the UI's public registration form.
Public registration always creates an active nonadmin account.

1. Sign in as the administrator. In **Teams**, create a team and add the intended
   developer's user ID (shown on their profile). Add the admin too if registering
   an application as that account: admins also require owning-team membership.
2. Sign in as the team member and select **Register application**. Supply the
   accountable owner/data-owner IDs, an HTTPS GitHub repository URL and relative
   bundle root. The creator receives developer and viewer roles.
3. In **Applications**, inspect the persistent ID, ownership, initial roles and
   history. Repository references are visibly **unverified**; registration makes
   no GitHub call. Developers can edit metadata with an optimistic version check.
4. The recorded owner or administrator can manage ownership and assign/revoke
   user/team application roles. Data ownership confers read access only. Team
   membership alone does not grant application visibility; an explicit team role
   does. No platform role grants GitHub, Databricks, or data permissions.

The UI uses paginated lists with First/Next controls. If another edit makes a form
stale, reload its version and review fields before resubmitting. Administrative
history includes team/membership and local-bootstrap events; application history
is visible only to actors who can currently read that application.

## Simulated sandbox bindings (T03)

Only the local runtime with explicitly selected simulation is currently supported.
Startup rejects organization mode, mismatched profile/executor combinations, and
real sandbox execution because the required integrations are not implemented.
No workspace, provider credentials or connectivity are needed.

After migration, an administrator can create a simulated environment in the UI's
**Environments** view. It records an opaque `simulated://<name>` workspace reference,
approved bundle targets, an enabled flag and a self-approval policy. Self-approval
is **off by default** and applies only to later local simulated approval workflows.
Alternatively, from `backend/`, explicitly seed the same local sandbox:

```bash
uv run --locked python -m seed_sandbox --admin-user-id <your-admin-user-id>
```

The command requires an existing active administrator and direct access to the
local database. It creates `local-sandbox`, reference `simulated://local-sandbox`,
and approved target `sandbox`. Repeating the identical seed is a no-op; it refuses
to overwrite a changed environment. Pass `--allow-self-approval` only to explicitly
opt in when creating the seed. Creation and policy are audited under the supplied
local administrator ID. No accounts or resources are created by this command.

In an application's detail view, an administrator can **Bind an environment** and
choose one of its approved targets. Only one binding per application/environment
is allowed. The closed configuration schema accepts only:

| Field | Default | Allowed value |
|---|---|---|
| `schema_version` | 1 | Integer 1 |
| `synthetic_row_count` | 100 | Integer 1–10,000 |
| `max_runtime_seconds` | 300 | Integer 1–3,600 |

These are preparation settings for later tasks; nothing runs in T03. Unknown keys,
credential fields, arbitrary strings, commands and unsupported schema versions are
rejected. Editing `config` replaces the entire typed config, filling its defaults.

Application readers can see bindings and the environments bound to their visible
applications. Only platform admins can change either. Disabling an environment or
removing an approved target preserves bindings/history and makes affected bindings
unusable. Every environment edit increments its version and all associated binding
versions in the same audited transaction; stale forms must be reloaded and reviewed.
All environment/binding responses and screens explicitly identify simulation.

## Containers

Backend and frontend images build from the locked workspace with uv (pinned to
`0.12.11`, matching CI): a builder stage runs `uv sync --locked --package
<backend|frontend> --no-dev`, and the runtime stage copies only that resulting
virtual environment plus the member's source — no `.env`, credentials, local
`data/`, or host `.venv` are copied in.

For a first start using the bundled database, create `.env` from `.env.example`
if it does not exist. Set a generated `SECRET_KEY`, matching `POSTGRES_PASSWORD`
and database-URL password, and `DATABASE_URL` with host **`db`**, port **5432**.
Keep `RUNTIME_PROFILE=local` and `DEPLOYMENT_EXECUTOR=simulated`. The database
user/name must match `POSTGRES_USER`/`POSTGRES_DB`. Do not overwrite an existing
`.env` or change a populated database's password by editing only that file.

From the repository root in your regular WSL terminal:

```bash
docker compose --profile local-db config --quiet
docker compose --profile local-db build
docker compose --profile local-db up -d --wait db
docker compose --profile local-db run --rm --no-deps backend alembic upgrade head
docker compose --profile local-db up -d --wait
curl --fail http://localhost:8000/ready
```

Migrations must run before the API/worker's first use; `compose up` does not apply
them automatically. The UI is at <http://localhost:8501>, API docs at
<http://localhost:8000/docs>, and the bundled database is published on localhost
port 5433. Containers reach that database at `db:5432`, not `localhost:5433`.
`--wait` checks container startup; `/ready` additionally checks the queue schema
and recent worker heartbeat.

Create your first administrator interactively (replace the email):

```bash
docker compose exec backend python -m bootstrap --email you@example.com --username local-admin --admin
```

The password is prompted, not put in command history. Sign in with that account
to create teams and register applications. No application account is seeded.
To stop services while retaining the database, use
`docker compose --profile local-db stop`; use `up -d --wait` to start them again.

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

Local Docker verification passed on 2026-09-11: quiet Compose validation,
backend/frontend/worker image builds, fresh bundled PostgreSQL migration through
007, API liveness/readiness and Streamlit health. Docker Desktop was reachable
from regular Ubuntu; an earlier agent-session CLI mount returned an I/O error.
That session error did not indicate a broken Docker daemon. Devstack integration
and external providers remain unverified.

## Available endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Application identity |
| GET | `/health` | API process liveness |
| GET | `/ready` | Queue schema accessible and worker heartbeat within 60 seconds |
| GET | `/api/v1/queue/telemetry` | Admin-only queue counts, age and worker freshness |
| POST | `/auth/register` | Create a development account |
| POST | `/auth/login` | Email/username and password as form data |
| GET | `/auth/me` | Current user; requires bearer token |
| GET | `/docs` | OpenAPI UI |

AI routes and placeholder metrics are absent. CSV/example modules remain dormant
and are not mounted by the platform API. The registry is under `/api/v1`; see
[API contracts](mdfiles/api-contracts.md) and `/docs` for payloads and permissions.

## Verification

```bash
uv run --locked pytest -q
uv run --locked mypy
uv run --locked ruff check backend/core/config.py backend/core/database.py backend/main.py backend/models backend/api/dependencies.py backend/api/platform_errors.py backend/api/endpoints/auth.py backend/api/endpoints/applications.py backend/api/endpoints/teams.py backend/services/auth_service.py backend/services/application_service.py backend/services/policy_service.py backend/services/audit_service.py backend/services/pagination.py backend/bootstrap.py backend/seed_sandbox.py backend/services/operation_service.py backend/services/queue_service.py backend/api/endpoints/operations.py backend/worker.py backend/queue_probe.py backend/alembic/versions/007_durable_operations.py backend/services/environment_service.py backend/api/endpoints/environments.py backend/alembic/env.py backend/alembic/legacy_models.py backend/alembic/versions/005_owned_applications.py backend/alembic/versions/006_environment_bindings.py frontend tests/conftest.py tests/unit tests/integration
uv run --locked ruff format --check backend/core/config.py backend/core/database.py backend/main.py backend/models backend/api/dependencies.py backend/api/platform_errors.py backend/api/endpoints/auth.py backend/api/endpoints/applications.py backend/api/endpoints/teams.py backend/services/auth_service.py backend/services/application_service.py backend/services/policy_service.py backend/services/audit_service.py backend/services/pagination.py backend/bootstrap.py backend/seed_sandbox.py backend/services/operation_service.py backend/services/queue_service.py backend/api/endpoints/operations.py backend/worker.py backend/queue_probe.py backend/alembic/versions/007_durable_operations.py backend/services/environment_service.py backend/api/endpoints/environments.py backend/alembic/env.py backend/alembic/legacy_models.py backend/alembic/versions/005_owned_applications.py backend/alembic/versions/006_environment_bindings.py frontend tests/conftest.py tests/unit tests/integration
```

Unit tests (`tests/unit`, the default `testpaths`) block network calls. Startup and
migration-rendering tests use an isolated process with controlled configuration; no
running database or provider is required. UI tests use Streamlit's test runner and
in-process API calls for registry workflows. Offline registry tests use SQLite
with foreign keys enabled; PostgreSQL tests establish real migration, constraint,
transaction and concurrent-update behavior. Mypy covers 24 new/affected platform
modules; unrelated legacy modules remain outside its scope.

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
rendering is not proof of a successful migration on a live database; the isolated
PostgreSQL CI job supplies that check. Legacy auth/example HTTP scripts are kept under `tests/manual/` and are not
collected by pytest; the example endpoint is not mounted in the platform API.

## Durable simulated operations (T04)

Migrate to head 007, start the API and worker, and register an application plus a
usable binding. The owner/admin must explicitly grant the submitting user an
**operator** role. From `backend/`, queue the fixed internal success probe:

```bash
uv run --locked python -m queue_probe --actor-id <operator-user-id> --application-id <application-uuid> --binding-id <binding-uuid> --idempotency-key <unique-key>
```

This direct-database local command uses the named operator's current policy.
It makes no GitHub/Databricks calls. An identical key repeats the original result;
use a new key to request another probe after the previous reservation is resolved.
There is no HTTP arbitrary task-execution endpoint. Compose starts the same
worker; `python -m worker --once` performs one queue cycle for diagnostics/tests.

In **Applications → Operations**, refresh to see status, attempts, observation
and heartbeat timestamps. Operator controls cancel, create a linked retry for a
resolved failure/cancellation, or request reconciliation with a reason. Running
cancellation is intent until observed. Unknown outcomes retain their reservation;
no force-success or blind reservation-release control exists. The probe alone is
not a generated application, deployment, or proof of external connectivity.
