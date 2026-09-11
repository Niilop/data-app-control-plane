# Next agent: T01b containers, PostgreSQL verification, and CI

Prepared 2026-09-11. This is a focused starting point; no prior conversation is
required. Read the versioned root `AGENTS.md`, then this file and the linked context.

## Starting state

- PR #1 (documentation) and PR #2 (T01a implementation) are merged into `main`.
- Verified merged baseline: `fd28d94`. It includes T01a `7935a6c` and follow-up
  `f1e4381`, which already changed the Compose backend URL to use `POSTGRES_DB`.
- Local `main` has been fast-forwarded to that baseline.
- Continue on **`build/t01b-containers-ci`**, prepared locally from updated `main`.
  On a fresh clone where this branch is absent, create it from updated `main`.
  This handoff is committed on main; T01b implementation is pending.
- `AGENTS.md`, `mdfiles/`, and `uv.lock` are deliberately versioned per the user's
  latest decision. `.gitignore` excludes local secrets/caches, not shared agent
  context. Inspect current status and preserve any new unrelated user changes.

## Product constraints

Build a local-first control plane for governed Databricks data applications, with
GitHub repositories and GitHub Actions. The developer has essentially no cloud
budget. PostgreSQL/Redis already run under `~/code/devstack`; use an isolated
application/test database and do not modify shared services or other databases.
Redis is not required by this application.

AI chat, RAG, LLM, inference helpers, and their provider dependencies were explicitly
removed. Do not restore them or add a legacy AI feature toggle. Historical tables
and migration versions are preserved. New registry/workflow features start after
T01, not in this task. No Databricks account is needed for T01b.

## What already works

- Python 3.11 selection, tracked uv lock, project-local pytest/Ruff/mypy tools.
- API assembly without AI settings/provider imports; development auth and
  process-liveness endpoints; SQL debug off by default.
- Streamlit account/status UI; configurable `API_URL`, bounded HTTP requests.
- 17 offline tests passed during T01a, including startup, UI, and migration SQL
  rendering. Ruff passed on changed files; mypy passed on settings/API assembly.
  These are recorded prior results, not a new verification of T01b or merged main.
- Removed table metadata lives in `backend/alembic/legacy_models.py`, loaded only
  by Alembic. `EMBEDDING_DIM` remains a compatibility constant required by migration
  002. Do not recreate `backend/alembic/__init__.py`: it shadowed installed Alembic.

## T01b scope and acceptance

Deliver one focused PR against **`main`**:

1. Replace pip/requirements-based Docker installs with reproducible uv installs
   from the tracked workspace lock. Backend/frontend builds select the appropriate
   runtime dependencies. Do not copy `.env`, credentials, local data, or `.venv`
   into images. Pin and document the uv version used by builds/CI.
2. Make local database configuration usable with existing devstack and an optional
   self-contained Compose DB setup. Avoid host-port conflicts and mandatory
   dependencies on a disabled DB service. Keep DB name, healthcheck, credentials,
   and API connection settings consistent. The hardcoded backend DB-name bug is
   already fixed; check the other configuration paths independently.
3. Add isolated PostgreSQL integration tests that execute the existing migration
   chain and verify the expected tables/head. Use pgvector-capable PostgreSQL;
   SQLite and offline SQL rendering do not satisfy this check. Test preservation
   when upgrading from a previous revision using only disposable test data.
4. Add this platform repository's GitHub Actions CI: locked setup, scoped
   lint/format/type checks, offline tests, and the isolated migration check. This
   is not the generated application deployment workflow from later tasks.
5. Update startup/test instructions and record actual check results. Run image
   builds and a local startup smoke check when Docker is available. If an external
   facility is unavailable, finish independent work and report exactly which gate
   remains unverified; do not label an unrun build or hosted workflow successful.

Keep historical migrations unchanged. Prefer existing dependencies and avoid
unrelated upgrades, package-wide import rewrites, dormant CSV/example cleanup,
domain models, worker implementation, identity changes, and cloud provisioning.
Do not merge your own PR or activate paid workloads. Project-local dependency
downloads and Docker image pulls may require environment approval; do not install
global tools or change shared devstack configuration to get around a blocker.

## Read these files first

| Purpose | Files |
|---|---|
| Task contract and existing evidence | T01 section in [development-plan.md](development-plan.md) |
| Process and transaction direction | [architecture.md](architecture.md) |
| Test baseline and commands | [testing-and-operation.md](testing-and-operation.md), root `README.md` |
| Dependency/container setup | Root/backend/frontend `pyproject.toml`, `uv.lock`, `.python-version`, both Dockerfiles and `.dockerignore` files, `docker-compose.yaml` |
| Settings and persistence | `backend/core/config.py`, `backend/core/database.py`, `.env.example` |
| Migrations | `backend/alembic/env.py`, `legacy_models.py`, `versions/001_initial.py` through `004_add_background_jobs.py` |
| Test setup | `tests/conftest.py`, `tests/unit/test_startup.py`, root pytest/mypy/Ruff configuration |

Do not read `.env` into tool output. The [repository map](repository-map.md) covers
additional paths if needed; a full repository crawl is unnecessary.

## Known testing and execution pitfalls

- Root pytest `testpaths` currently includes only `tests/unit`. Add explicit
  integration discovery/markers and documented commands as part of this task.
- `tests/conftest.py` currently blocks sockets for every test. Scope that guard to
  offline tests while requiring deliberate isolated DB configuration for integration
  tests. Preserve tests proving the offline suite cannot contact providers.
- Starlette TestClient stalled inside the prior execution sandbox and passed
  outside it with outbound-network guards still active. If repeated, report the
  environment restriction and use the approved execution mechanism; do not weaken
  tests, remove assertions, or increase timeouts indefinitely.
- Prior sandbox uv commands used `UV_CACHE_DIR=/tmp/data-app-uv-cache` because the
  default cache was not writable. `.venv` is project-local. Use `uv`, never system
  Python or pip. Cache contents are not part of reproducibility evidence.
- GitHub CLI authentication worked, while the saved SSH remote could not
  authenticate. A direct HTTPS push using `gh auth git-credential` worked. Prefer
  the available authenticated mechanism without printing credentials or rewriting
  the user's saved remote globally. Do not treat a sandbox network failure as
  proof that credentials are invalid.

## Handoff and review

Explain the multi-file plan before editing. Implement T01b only. Before opening a
draft PR, review the diff for unrelated user changes and secrets, run the relevant
checks, and update the T01 ledger plus affected repository/runbook documentation.
Report commands, outcomes, missing verification, and remaining limitations. T01
can be marked complete only when both T01a and T01b acceptance criteria are met.

Use a fresh review agent after implementation to inspect the PR against these
criteria. Do not delegate during implementation unless the user asks for it.

## Copy-paste assignment

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Continue
> T01b only on build/t01b-containers-ci, based on merged main. Inspect Git status
> and preserve my unrelated local changes. Explain the plan, implement the bounded
> container/database/CI work, run its acceptance checks, update the handoff, and
> open a draft PR against main. Do not merge, start T02, or deploy cloud resources.
