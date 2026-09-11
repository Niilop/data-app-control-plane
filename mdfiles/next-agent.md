# Agent handoff

This describes the proposed code state of this PR, not its merge status. Inspect
Git status, preserve unrelated changes, and verify prerequisites on updated main
before starting the next task. Read AGENTS.md and the linked task contracts.

## Implemented state

Build a local-first control plane for governed Databricks data applications, with
GitHub repositories and GitHub Actions. The developer has essentially no cloud
budget. PostgreSQL/Redis already run under `~/code/devstack`; use an isolated
application/test database and do not modify shared services or other databases.
Redis is not required by this application.

AI chat, RAG, LLM, inference helpers, and their provider dependencies were
explicitly removed (T01a). New registry/workflow features start after T01, not
in this task. This PR is **T01b**: locked container builds, devstack/optional
database configuration, isolated PostgreSQL migration integration tests, and
this repository's own GitHub Actions CI. No Databricks account is needed.

- **Dockerfiles** (`backend/Dockerfile`, `frontend/Dockerfile`): rewritten as
  two-stage builds. The builder stage copies the pinned uv binary from
  `ghcr.io/astral-sh/uv:0.12.11` and runs `uv sync --locked --package
  <backend|frontend> --no-dev` (this is a uv workspace, so both members'
  `pyproject.toml` files must be present in the build context even though only
  one member's dependencies are installed and only that member's source is
  copied into the final image). The runtime stage copies just that virtual
  environment to `/opt/venv` — deliberately outside `/app`, since
  `docker-compose.yaml` bind-mounts the host source over `/app` for hot reload
  and would otherwise shadow a venv placed under it — plus the member's source.
  No `.env`, credentials, local `data/`, or host `.venv` are copied in. A new
  root `.dockerignore` backs the `context: .` builds in Compose.
- **`docker-compose.yaml`**: the bundled `db` service (pgvector-enabled
  Postgres) moved behind an opt-in `local-db` Compose profile — it no longer
  starts by default and is never a mandatory dependency. Its host port is
  configurable (`POSTGRES_HOST_PORT`, default `5433`) to avoid colliding with
  devstack's Postgres on `5432`. The hardcoded
  `DATABASE_URL=...@db:5432/${POSTGRES_DB}` override on `backend` was removed
  (it unconditionally pointed at the disabled `db` service even when a
  developer intended to use devstack); `DATABASE_URL` now comes from `.env` only,
  as documented. `backend` gets `extra_hosts:
  host.docker.internal:host-gateway` so `.env` can point a containerized backend
  at a devstack Postgres published on the host. `backend`'s `depends_on: db` is
  `required: false` so it does not block startup when the `local-db` profile is
  inactive.
- **Isolated PostgreSQL migration integration tests**
  (`tests/integration/test_migrations.py`, new): marked `integration`, gated on
  `TEST_DATABASE_URL`, skipped with a visible reason when unset. Each test runs
  inside a uniquely named, disposable Postgres **schema** in that database
  (`search_path` scoped via the connection's `options`) rather than a freshly
  created database, so the test role needs only ordinary schema privileges, not
  `CREATEDB`. Covers: pgvector extension availability, the full Alembic chain
  reaching head with the expected tables, and that upgrading from an earlier
  revision (`001_initial`) preserves a row inserted at that revision instead of
  losing it on the way to head.
- **`tests/conftest.py`**: the autouse `block_network` fixture now skips tests
  marked `integration` (via a small `is_integration_test` helper, itself covered
  by a new regression test) — those tests legitimately need to reach a real
  database. `tests/unit` is unaffected: default `testpaths` still resolves to
  `tests/unit` only, so `pytest -q` collects the same offline suite as before
  plus the two new files that live under it.
- **CI** (`.github/workflows/ci.yml`, new; `.github/workflows/agent-handoff.yml`
  unchanged): a `lint-type-offline-tests` job runs the same locked
  sync/ruff/mypy/pytest commands documented in the README, pinned to uv
  `0.12.11` (matching the Dockerfiles and the existing handoff workflow); a
  separate `postgres-migration` job runs `pytest tests/integration -q` against a
  throwaway `pgvector/pgvector` GitHub Actions service container with
  `TEST_DATABASE_URL` pointed at it.
- **Docs**: README (new "Containers" section, updated verification commands),
  `mdfiles/testing-and-operation.md` (T01b commands, explicit
  run/not-run split), `mdfiles/repository-map.md`, `mdfiles/decisions.md`
  (ADR-011), and `mdfiles/development-plan.md` (T01 status, T01b handoff
  summary) updated in this PR alongside this file.
- **Preserved:** existing migrations, `backend/alembic/legacy_models.py`, the
  handoff-check workflow/script/PR template from PR #4, and the T01a
  offline-test baseline (all still pass; see below). No domain models, worker,
  or identity changes; no dormant CSV/example cleanup.

## Verification performed

Run from the repository root, actually executed in the implementing sandbox:

```bash
uv sync --locked --all-packages --group dev
uv run --locked pytest -q
uv run --locked mypy
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
```

Results: Python 3.11.16, uv 0.12.11 (already installed in the sandbox), pytest
9.1.1, Ruff 0.16.7, mypy 2.3.1. **37 tests passed** (up from T01a's 17 plus PR
#4's handoff-checker tests; the increase is the 2 new `tests/unit` files —
`test_conftest_network_guard.py` — plus network-guard scoping; `tests/integration`
is not in default `testpaths`). Ruff lint and format both clean over the listed
scope, including the two new files. Mypy reports no issues (scope unchanged:
`backend/core/config.py`, `backend/main.py`).

`uv sync --locked --package backend --no-dev` and `uv sync --locked --package
frontend --no-dev` were each run directly (not inside Docker, since Docker was
unavailable) to confirm the workspace-scoped sync the Dockerfiles rely on
actually resolves to the right dependency subset before committing to that
design — confirmed for both, then the full dev environment (`--all-packages
--group dev`) was restored.

`uv run --locked pytest tests/integration -q -rs` was run **without**
`TEST_DATABASE_URL`: 3 tests skipped, each with the intended visible reason.
This confirms the skip path only; it does not confirm the tests pass against a
real PostgreSQL/pgvector server.

## Remaining work and limitations

**Not run, and not claimed as passing:**

- Docker image builds (`docker compose build` / `docker build`) for either
  service. The implementing sandbox is WSL2 without Docker Desktop's WSL
  integration enabled — the `docker` CLI is not on `PATH` at all (only a
  Windows-side binary that isn't wired in), so this is a full absence, not a
  daemon-connectivity error to retry around.
- `docker compose up` and any live startup/health smoke check through the
  containers, for the same reason.
- `tests/integration` against a real PostgreSQL/pgvector server — no local
  PostgreSQL and no `~/code/devstack` checkout existed in the sandbox (`ls
  ~/code` showed no `devstack` directory). Only the skip path was exercised
  (see above). The `postgres-migration` CI job is the first real exercise of
  these tests; treat its actual hosted result on the PR as the evidence, not
  this handoff.
- `docker compose config` / Compose and workflow YAML validation — the `docker`
  CLI is absent and PyYAML is not installed in this project's offline venv, so
  `docker-compose.yaml`, `ci.yml`, and the Dockerfiles were reviewed manually
  (twice) rather than machine-validated.
- Devstack integration specifically (the `host.docker.internal` path, and
  whether devstack's actual Postgres port/credentials match what's documented)
  — there is no devstack checkout to verify against in this environment.

**Known gaps to note explicitly, not silently treat as done:**

- The `local-db` Compose profile's healthcheck and default port were chosen to
  avoid a *likely* collision with devstack (port `5432`), but the real devstack
  Postgres port was not confirmed here. If devstack uses a different port, only
  the `.env.example` comment needs adjusting, not the Compose file.
- `backend/requirements.txt` and `frontend/requirements.txt` are now unused by
  the Dockerfiles (uv/`uv.lock` is the sole source of truth for images) but were
  left in place rather than deleted, since removing them is unrelated cleanup
  outside this task's scope; a future task can drop them once confirmed nothing
  else reads them.
- `backend/.dockerignore` and `frontend/.dockerignore` predate this change and
  were not touched. Since both Dockerfiles build with `context: .` (the
  repository root), Docker only honors a root-level `.dockerignore` (or a
  `Dockerfile.dockerignore` colocated with the Dockerfile) for that build — the
  per-directory files were never actually in effect. The new root
  `.dockerignore` is what actually governs build-context exclusions now.

## Next task

Verify this PR is merged into updated `main` before building on it (repeat the
"Source of truth"/prerequisite-check step this task itself started with — do
not assume it from this file). Then implement **T02 — Register an owned
application** on a new branch from updated `main`; do not begin the entire
roadmap from this handoff.

T02 adds user-active/admin support, teams/memberships, applications,
application-role assignments, a centralized actor/policy dependency,
transactional audit, and a new migration; an application register/list/detail
UI and minimal admin team/role controls; permission-filtered pagination,
optimistic metadata updates, request IDs, and platform error envelopes.
Excludes repository network verification, environments, worker, approvals, and
external identity/groups/permissions. See the full T02 contract (read/implement/
exclude/acceptance) in `mdfiles/development-plan.md`.

Before starting T02's domain work, a reviewer with Docker/PostgreSQL access
should actually run the checks this handoff could not: `docker compose build`,
`docker compose up` plus a health check, and `tests/integration` against a real
pgvector database (or rely on the `postgres-migration` CI job's hosted result).
None of that blocks starting T02's own implementation, but T01 should not be
called fully verified until it happens.

## Files to read first

| Purpose | Files |
|---|---|
| T02 task contract | T02 section in [development-plan.md](development-plan.md) |
| Domain/API contracts for T02 | [domain-contracts.md](domain-contracts.md), T02 rows in [api-contracts.md](api-contracts.md) |
| T01b container/CI change itself | `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore`, `docker-compose.yaml`, `.env.example`, `.github/workflows/ci.yml` |
| T01b test change itself | `tests/conftest.py`, `tests/integration/test_migrations.py`, `tests/unit/test_conftest_network_guard.py`, `pyproject.toml` (`markers`) |
| Current auth/router/model files T02 extends | `backend/main.py`, `backend/api/endpoints/auth.py`, `backend/services/auth_service.py`, `backend/models/database.py`, `backend/models/schemas.py` |
| Test/build baseline and commands | [testing-and-operation.md](testing-and-operation.md), root `README.md` |
| Migrations | `backend/alembic/env.py`, `legacy_models.py`, `versions/001_initial.py` through `004_add_background_jobs.py` |

Do not read `.env` into tool output. The [repository map](repository-map.md) covers
additional paths if needed; a full repository crawl is unnecessary.

## Suggested agent prompt

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Inspect Git
> status and verify this T01b PR is merged into updated main. Implement T02
> only on its own branch. Preserve unrelated changes, explain the plan, run
> the acceptance checks, update the handoff and affected docs in the same PR,
> and open a draft PR against main. Do not merge, start T03, or deploy cloud
> resources. Before relying on T01b's container/CI claims, confirm with the
> user whether `docker compose build`/`up` and the isolated PostgreSQL
> migration tests have actually been run since — this handoff explicitly
> could not run them.
