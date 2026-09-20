# Testing and operation guide

Status: T01a established 17 passing offline tests, project-local dev tools, and
Python 3.11. T01b adds locked container builds, an optional bundled database
profile, isolated PostgreSQL migration integration tests, and platform CI; see
`### T01b commands` below for what has actually been run and what has not.
Historical auth/example scripts are under `tests/manual/` with names outside
pytest discovery; obsolete RAG tests were removed.

## T04a verification

React/browser checks and Docker test-image commands are in root README. Chromium
workflows use a disposable real FastAPI/SQLite server; they do not replace the
PostgreSQL migration/concurrency suite. Streamlit-only tests were retired after
equivalent browser workflows passed. See `next-agent.md` for current counts,
actual Docker checks and CI evidence. Browser artifacts are ignored by Git.

## T04 verification (historical)

Hosted [Platform CI run 34632237191](https://github.com/Niilop/data-app-control-plane/actions/runs/34632237191)
at `d1c417d` passed: **15 PostgreSQL tests**, **126 offline tests**, Ruff and mypy.
Actual logs were inspected; exact evidence is in `next-agent.md`. The offline suite
covers queue/API/UI behavior, policy revocation, atomicity, sanitized errors,
retry limits and stale tokens. The isolated PostgreSQL suite adds independent
competing worker processes, fresh API/worker processes after a lost lease,
heartbeat/cancellation, concurrent idempotency, migration round trips and rollback.
The migrated schema head is now 007, including new ORM/schema parity checks.

Run the commands in root README/CI. Integration tests require a dedicated
`TEST_DATABASE_URL`; missing configuration produces explicit skips, not success.
The later local Docker follow-up passed quiet Compose validation, all three image
builds, fresh bundled PostgreSQL migration through 007, API `/health` and `/ready`,
and Streamlit health. Regular Ubuntu could access Docker Desktop; the I/O error
was limited to the agent session's CLI mount. No reset or new global installation
was needed. Root README documents `.env`, database startup, migration, then service
startup. No application account was seeded or interactive user journey exercised.
Devstack is absent and remains unverified. Migration 001–006 is preserved and no
dependency was added. Historical task notes below describe their original checks.

## T03 verification

Current check commands and complete Ruff scope are in root README and CI. T03
requires explicit `DEPLOYMENT_EXECUTOR=simulated` even in isolated configuration;
fixtures and subprocess tests supply it without reading developer credentials.

Locally, `uv run --locked pytest -q` passed **108 tests** with the offline network
guard enabled (outside this sandbox's TestClient restriction). This includes
profile rejection, secret-safe settings errors, environment/binding authorization,
closed config, approved targets, version invalidation, transactional rollback,
explicit seed and Streamlit create/edit/stale-form cases. `uv run --locked mypy`
passed for **24 source files**. Ruff lint/format passed over the current scope.

`uv run --locked pytest tests/integration -q -rs` reported **10 skipped** locally
because `TEST_DATABASE_URL` is unset. New PostgreSQL tests preserve T02 application/
audit data through migration 006, enforce unique/FK constraints, verify rollback,
and race binding writes against each other and environment policy updates.
At T03, tests verified head 006 and T03 ORM/schema parity. Hosted
[Platform CI run 34624002359](https://github.com/Niilop/data-app-control-plane/actions/runs/34624002359)
at `974c16e` confirmed **10 PostgreSQL tests passed**, no skips, **108 offline
tests passed**, Ruff clean/42 files and mypy clean/24 files. The actual job logs
were inspected; see `next-agent.md`. Agent handoff also passed. Local skips alone
prove no PostgreSQL behavior.

No real seed, provider connectivity, paid execution, Docker image build or live
container startup was run. Root README documents the optional local simulated
seed and UI path; legacy Docker/devstack limitations remain.

## T02 verification

The current checks are the commands in root README and `.github/workflows/ci.yml`.
T02 expands Ruff to every changed/new runtime module, new migration, frontend and
test files, and mypy to 18 platform modules. No dependency was added.

Locally: `uv run --locked pytest -q` passed **67 tests**, including 27 registry
API cases and three Streamlit workflows through the in-process API. Tests retain
the outbound-network guard; TestClient requires execution outside this sandbox's
thread restriction. `uv run --locked mypy` passed. PostgreSQL tests run separately:
`uv run --locked pytest tests/integration -q -rs` reported **6 skipped** without
`TEST_DATABASE_URL`. They cover fresh/old-head migration, legacy users and flags,
new ORM/schema parity, real constraints, API rollback and competing metadata writes.
Hosted [Platform CI run 34615449895](https://github.com/Niilop/data-app-control-plane/actions/runs/34615449895)
at `77a9a03` confirmed **6 PostgreSQL tests passed**, no skips, **67 offline tests
passed**, Ruff clean and mypy clean. Actual logs were inspected; see
`next-agent.md`. The handoff check also passed. Local skips alone are not migration
verification. Docker's Windows launcher reports unavailable WSL
integration; image builds and live startup remain unrun.

Local account/bootstrap and the registration demonstration are documented in root
README. Bootstrap prompts for new passwords, refuses existing accounts, and audits
explicit admin creation. It does not deploy or contact an external provider.

## Development environment

- Linux/WSL2; use `uv` for all Python execution and project-local tools.
- Prefer PostgreSQL from `~/code/devstack` with a dedicated application database
  and a separate test database. Discover available connection configuration without
  printing credentials; do not modify shared services/databases. `~/code/devstack`
  did not exist in the sandbox that implemented T01b; devstack integration is
  documented but unverified there (see next-agent.md).
- Legacy migrations include pgvector. Verify extension availability rather than
  silently replacing PostgreSQL with SQLite or editing the historical migrations.
- `.env` is local and excluded from Git. Maintain `.env.example` with placeholders
  and descriptions only. Bind local services to loopback by default.
- No Redis queue is required even if Redis is already running in devstack.
- uv `0.12.11` is pinned across both Dockerfiles (via `ghcr.io/astral-sh/uv:0.12.11`)
  and both GitHub Actions workflows, matching the version verified in T01a.

## Verified T01a commands

Run from the repository root:

```bash
uv sync --locked --all-packages --group dev
uv run --locked pytest -q
uv run --locked mypy
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py tests/browser_server.py tests/conftest.py tests/unit
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py tests/browser_server.py tests/conftest.py tests/unit
```

All passed in T01a. Mypy checks settings/API assembly initially; Ruff covers the
listed new/modified code. In the development sandbox, TestClient's event-loop
startup stalled; the same tests passed outside the sandbox with outbound-network
guards still enabled. No providers or live databases were contacted by the suite.

## T01b commands

Run from the repository root (adds `tests/integration` to the Ruff scope and
registers the `integration` pytest marker; `testpaths` still defaults to
`tests/unit` only, so `pytest -q` is unaffected):

```bash
uv sync --locked --all-packages --group dev
uv run --locked pytest -q
uv run --locked mypy
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py tests/browser_server.py tests/conftest.py tests/unit tests/integration
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py tests/browser_server.py tests/conftest.py tests/unit tests/integration
```

**Actually run and passing** in the sandbox that implemented T01b: all four
commands above (37 offline tests passed, up from 17; mypy and Ruff clean).

**Not run** in that sandbox — no Docker daemon, no local PostgreSQL, and
`~/code/devstack` absent there:

```bash
docker compose build
docker compose up
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/disposable_test_db \
  uv run --locked pytest tests/integration -q
```

The isolated migration tests were first exercised only for their skip path (no
`TEST_DATABASE_URL` set: 3 tests skip cleanly with a visible reason) locally.
**Hosted CI then confirmed them for real, and PR #5 was merged into `main`**
(merge commit `07e90c5`). All reported checks passed for PR head
`a50795c1d4740aaa079343627e3d21d856a5e31d`:
[Platform CI run 34608464924](https://github.com/Niilop/data-app-control-plane/actions/runs/34608464924)
passed both jobs. The actual
[`postgres-migration` log](https://github.com/Niilop/data-app-control-plane/actions/runs/34608464924/job/103292661662)
reports **3 passed in 1.47s**, no skips, against `pgvector/pgvector:pg16`.
This confirms both `backend/alembic/env.py` fixes through the real migration
tests, including repeated upgrades and preservation of an existing row. The
lint/type/offline-test job and the agent-handoff check also passed.

This follow-up inspected hosted job metadata and actual migration logs; no
additional code fix was needed. Application tests were not rerun locally.
Docker image builds, container startup, and local PostgreSQL/devstack checks
remain unverified.


The following startup/migration commands remain documented but a live DB
migration and real account login are still not verified end to end.

Current backend import style expects the backend directory on Python's import
path. The intended initial startup commands, from `backend/`, are:

```bash
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --reload
```

Only point Alembic at the dedicated development database. T04 adds, from the same
directory, `uv run --locked python -m worker`. From `frontend/`, run `npm ci` then
`npm run dev` using Node 24.21.0 / npm 11.19.0. Vite proxies to the local API;
`API_PROXY_TARGET` can override its server-side target. Docker uses nginx on 8501.
Containers must run these processes independently, with separate environment and
credential injection. Migrations run once as an explicit step, not from every replica.

## Test layers

### PR handoff check

Every implementation PR must update `mdfiles/next-agent.md` in the same PR. The
`Agent handoff` workflow compares the head commit to the merge base, so a change
only on the base branch cannot satisfy the rule. Markdown/reStructuredText and
LICENSE/NOTICE changes alone are exempt; all other file types conservatively
require an update. Deleting the handoff, omitting its six sections, or making a
whitespace-only update fails. CI cannot verify that the written claims are true.

To check committed changes locally (working-tree edits are not included):

```bash
uv run --no-project --python 3.11 scripts/check_agent_handoff.py --base origin/main --head HEAD
uv run --locked pytest tests/unit/test_agent_handoff.py -q
```

Fetch current base history first. The workflow has no path filter and reports a
result for documentation-only PRs too. It uses read-only contents permission,
no saved checkout credential, pinned action revisions, and uv 0.12.11; it does
not install the application dependencies or run provider workloads. Setup follows
the official [uv integration guide](https://docs.astral.sh/uv/guides/integration/github/)
and [checkout configuration](https://github.com/actions/checkout/blob/main/README.md).

To require this check before merging, select **Check agent handoff** in the
repository's required-status rules after the workflow is available. No such rule
is configured by this change. Reviewers still verify the handoff's accuracy.

### Application checks

| Layer | What it establishes |
|---|---|
| Unit | Policy decisions, state transitions, canonical hashes, parameter validation, error classification |
| API + PostgreSQL integration | Transactions, authorization, pagination, idempotency constraints, migrations, durable claiming |
| Adapter contract | Both simulator and scripted real-provider adapter obey submit/observe/cancel/reconcile contracts |
| Generated-project checks | Deterministic artifacts, valid project layout, locked build, lint/types/unit tests |
| UI smoke / end to end | Real local user journey through authenticated API and worker |
| Opt-in external | Genuine GitHub workflow and Databricks results under separately configured credentials |

Database tests need real PostgreSQL to exercise locking/constraints; SQLite is not
evidence for worker concurrency. Fixtures create isolated schemas/databases and
clean only objects they own. Restore demonstrations use a disposable target,
never overwrite the developer's active or shared DB.

No provider credentials or network calls in the default test suite. Mark external
tests explicitly and skip with a visible reason unless deliberately enabled.
Use scripted adapters to reproduce failures deterministically; do not disguise
scripted responses as external verification. Human review applies to identity and
infrastructure changes before activation.

## Required regression scenarios by introduction point

| Scenario | First task |
|---|---|
| No LLM key/provider needed at API startup; safe test collection | T01 |
| Tenant/application visibility and privilege escalation denial | T02 |
| Organization profile cannot use local auth/simulation | T03 |
| Atomic command/audit enqueue; duplicate key mismatch; two workers; stale fencing token | T04 |
| Generation traversal/injection, digest integrity, download access | T05 |
| Revision/config/target changes require new approval; role revocation before dispatch | T06 |
| Unknown job or invalid parameters rejected; run/deployment outcomes independent | T07 |
| Ref drift and source provenance; private repo/rate-limit errors | T08 |
| Dispatch timeout, late/duplicate run discovery, manifest mismatch, cancellation races | T09 |
| Genuine deployment/run output; no silent fallback; bounded external execution | T10 |
| Access request escalation denial, effective revocation, archive preservation | T11 |
| Repeatable load/recovery report and isolated restore | T12 |

## Local demonstration and operations

The final demo script seeds a local admin, engineer, approver, and viewer (roles
may share one human), one team, one application, and simulated sandbox. Secrets
are supplied interactively or via local tooling, not committed fixtures for real
accounts. Script demonstrates generation, validation, exact approval, deployment,
job run, access request/revoke, and archive using public API contracts.

Recovery procedures must explain how to inspect an operation/attempt, check lease
ownership, find external correlation/run IDs, request reconciliation, and retry
only after uncertainty resolves. Never instruct operators to set `succeeded` or
delete queue rows directly to unblock the UI.

At T12 record workload and hardware, latency percentiles, accepted/completed counts,
queue age, contention, and recovery time. Define timing targets before the measured
run and state sample sizes. Keep correctness invariants mandatory regardless of
throughput. Logs/results must be scrubbed of credentials and sensitive data.

For real sandbox sessions, document start/stop steps and verify resource termination
or known ongoing resources afterward. Archiving the registry entry is not cleanup
of paid external resources.

## T05 verification

T05 adds `scripts/check_generated_project.py` to CI. It renders only the approved
local template into a disposable project, creates a fresh cache, installs its lock
with uv offline and runs its stdlib tests. Worker validation itself executes no code.
The new unit/API tests cover closed input, traversal, archive types, corruption,
private downloads, immutable snapshots, policy changes, command replay, fenced
recovery, cancellation/retry and atomic audit failures. PostgreSQL tests check
immutable SQL triggers and concurrent command/artifact completion on real locks.
Browser tests use a disposable worker restricted to preparation kinds so existing
probe recovery fixtures remain stable. No fixture endpoint is exposed by the app.

Local 2026-09-14 evidence: 147 offline tests, 17 PostgreSQL tests (no skips), 10
Chromium workflows and isolated production nginx smoke passed. Mypy passed for
34 modules and the generated project's 2 tests passed after locked offline install.
See next-agent.md for final changes, current checks and limitations. Existing live
application DB migration/startup were deliberately not performed: the abandoned
T05 branch used a different migration history.
