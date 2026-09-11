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

AI chat, RAG, LLM, inference helpers, and their provider dependencies were explicitly
removed. Do not restore them or add a legacy AI feature toggle. Historical tables
and migration versions are preserved. New registry/workflow features start after
T01, not in this task. No Databricks account is needed for T01b.


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


This PR adds a handoff requirement to AGENTS.md, a PR checklist, and the
`Agent handoff / Check agent handoff` workflow. Its standard-library checker
compares the PR head with its merge base, requires substantive handoff changes
for non-documentation files, and validates the six handoff sections. It also
handles deletions/renames and refuses whitespace-only updates.

## Verification performed

T01a's recorded baseline is 17 passing offline tests plus focused Ruff/mypy.
For this change, 18 checker tests using disposable Git histories passed, along
with Ruff lint/format and mypy for the checker. See the task ledger for commands.
The application suite was not rerun for this tooling-only change. Hosted workflow
results must be inspected on the PR rather than assumed from local tests.

## Remaining work and limitations

The handoff check establishes an update and section structure, not factual accuracy.
Reviewers must compare claims to the code and test evidence. Making this status
check a required merge condition needs a repository rule; no rules are changed
by this PR. Full application CI, live PostgreSQL migrations, Docker builds, and
real DB login remain unverified and belong to T01b.


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


## Next task

Verify the handoff-policy PR is merged before building on its workflow. Then
implement **T01b only**. Create `build/t01b-containers-ci` from updated main if it
does not exist; otherwise inspect and update its base without losing local work.


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


## Files to read first


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


Also inspect `.github/workflows/agent-handoff.yml`,
`.github/pull_request_template.md`, and `scripts/check_agent_handoff.py` so T01b
extends CI without replacing the handoff check.

## Suggested agent prompt

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Inspect Git status
> and verify the prerequisite PRs are merged into updated main. Implement T01b
> only on its own branch. Preserve unrelated changes, explain the plan, run the
> acceptance checks, update the handoff and affected docs in the same PR, and
> open a draft PR against main. Do not merge, start T02, or deploy cloud resources.
