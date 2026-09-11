# Testing and operation guide

Status: T01a established 17 passing offline tests, project-local dev tools, and
Python 3.11. T01b adds locked container builds, an optional bundled database
profile, isolated PostgreSQL migration integration tests, and platform CI; see
`### T01b commands` below for what has actually been run and what has not.
Historical auth/example scripts are under `tests/manual/` with names outside
pytest discovery; obsolete RAG tests were removed.

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
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit
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
uv run --locked ruff check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
uv run --locked ruff format --check backend/core/config.py backend/main.py backend/models backend/alembic/env.py backend/alembic/legacy_models.py frontend/app.py tests/conftest.py tests/unit tests/integration
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
directory, `uv run --locked python -m worker`. From `frontend/`, the intended UI
command remains `uv run --locked streamlit run app.py`, with a configurable API URL.
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
