# Agent handoff

This describes implemented code, not this PR's merge status. Inspect Git status,
preserve unrelated changes, verify prerequisites on updated main, and read
AGENTS.md before starting the next bounded task. Do not assume T03 is merged.

## Implemented state

T01/T02 are merged; T02 is PR #6 at `712aa25`. Its handoff reconciliation PR #7
is also merged. T03 started from updated main `928f2f7` on its own branch.
**T03 — Register a sandbox environment binding is implemented in draft PR #8,
awaiting review and merge.** T04/worker, real adapters and deployment were not started. AI/chat/
RAG/LLM/inference remain removed.

T02 behavior is preserved: development login/accounts, explicit local admin
bootstrap, teams/memberships, owned applications, current direct/team role policy,
versioned metadata, paginated reads and transactional audit. Owner/data owner
confer no infrastructure rights. No external credentials or permissions are granted.

T03 adds:

- `006_environment_bindings`: versioned UUID/UTC environments and bindings;
  unique application/environment pair and noncascading foreign keys. Migration
  history 001–005 and existing data remain intact. ORM is in `models/platform.py`;
  strict schemas are in `models/environment_schemas.py`.
- Startup settings: `RUNTIME_PROFILE=local` (default) plus **explicit required
  `DEPLOYMENT_EXECUTOR=simulated`**. Existing local `.env` files must add this.
  Organization mode, profile/executor mismatches and real sandbox execution fail
  clearly at startup. Settings validation errors omit input values. `.env.example`
  and isolated test configuration document/provide the opt-in; no user `.env` was
  changed. No nominal executor or worker is introduced.
- Admin environment create/list/detail/update: name, opaque
  `simulated://<name>` workspace reference, explicit simulated executor, approved
  bundle-target allowlist, enabled flag, self-approval policy (off by default),
  and positive version. Self-approval true is an explicit local policy for future
  approval tasks, not implemented approval execution.
- Admin application binding create/update; authorized list/detail. One binding
  per application/environment. Unknown/disabled environment, unapproved target,
  archived application, invalid config and stale versions fail predictably.
  Nonadmins only see bindings for readable apps and environments bound to those
  apps; app ownership/developer role never grants environment-write authority.
- Closed config schema 1: integer `synthetic_row_count` (default 100, 1–10,000)
  and `max_runtime_seconds` (default 300, 1–3,600). No credential, arbitrary string,
  URL, command, compute or unknown config keys are accepted. Config PATCH replaces
  the whole typed object, applying defaults for omitted fields.
- Synchronous environment service transactions include every mutation and audit.
  Environment-row locks serialize environment changes with binding create/update.
  Each environment edit increments its own version and every associated binding
  version, with `binding.environment_changed` audit in each affected app's history
  and an admin environment event. Stale edits return 409. Policy disable/target
  removal retains bindings and history but makes them unusable. Future revisions/
  approvals must capture and recheck environment plus binding versions/policy.
- Responses embed current environment policy and explicitly show
  `execution_mode=simulated`; binding `usable` describes recorded eligibility, not
  connectivity, execution success or an immutable snapshot.
- Streamlit Environments view and per-app Environment bindings controls support
  creation/edit/read with approved-target selectors, bounded config fields,
  explicit simulation/self-approval labels and retained form versions. Shared
  pagination/feedback moved from `registry.py` to `registry_widgets.py`.
- `uv run --locked python -m seed_sandbox --admin-user-id <id>` from `backend/`
  explicitly seeds `local-sandbox`, reference `simulated://local-sandbox`, approved
  target `sandbox`. Requires an existing active platform admin and direct local
  DB access. Self-approval stays false unless `--allow-self-approval` is supplied.
  Identical repeats are no-ops; changed existing policy is never overwritten.
  Creation is audited under the supplied local admin ID. No users are created.

## Verification performed

Actually run locally:

- `uv run --locked pytest -q`: **108 passed**. Includes API authorization,
  invalid/unapproved/disabled targets, config and profile validation, sanitized
  errors, version changes, seed behavior, rollback after flush, and Streamlit
  create-binding/stale-policy workflows. The offline network guard stayed enabled;
  TestClient requires execution outside this sandbox's thread restriction.
- `uv run --locked mypy`: **24 source files passed**.
- Ruff lint and format passed over the current explicit scope in root README and
  `.github/workflows/ci.yml`, including new schemas/service/router/seed/migration,
  frontend and tests. Historical migrations and manual examples are unchanged.
- `uv run --locked pytest tests/integration -q -rs`: **10 skipped**, with explicit
  missing-`TEST_DATABASE_URL` reasons. These skips are not PostgreSQL verification.

**Hosted T03 verification passed** at implementation commit
`974c16ec76178328e90ed66f3db6e96714294cf3` in
[draft PR #8](https://github.com/Niilop/data-app-control-plane/pull/8).
[Platform CI run 34624002359](https://github.com/Niilop/data-app-control-plane/actions/runs/34624002359)
passed both jobs. The actual
[PostgreSQL job log](https://github.com/Niilop/data-app-control-plane/actions/runs/34624002359/job/103344569742)
reports **10 passed in 2.92s**, no skips, against `pgvector/pgvector:pg16`.
This verifies T02-data preservation through migration 006, T03 schema parity,
unique/FK constraints, rollback, concurrent binding updates and serialization of
policy edits with binding creation. The offline job reports **108 passed in
12.90s**, Ruff clean/42 files formatted and mypy clean/24 files. Agent handoff run
34624002288 also passed. Actual logs were inspected; CI configuration alone was
not treated as evidence.

Locked offline sync and the local handoff checker against updated `origin/main`
also passed. This follow-up records evidence without changing implementation;
application tests were not rerun for the documentation follow-up. Recheck current
CI on later revisions. This PR is not claimed merged.

## Remaining work and limitations

- Review draft PR #8 and confirm current CI before merge. Do not infer merge or
  live database correctness from code or local SQLite tests alone.
- Local PostgreSQL/devstack and Docker builds/live container startup remain
  unverified. No configured disposable test DB or devstack checkout is available
  here; the Docker launcher previously reported missing WSL integration.
- No actual local database was migrated/seeded during this implementation.
  Existing `.env` must explicitly enable simulation before API/Alembic/seed use.
- Only local simulation configuration is accepted. Real workspace references,
  provider connectivity, compute selection, real executors and external identity
  remain later integration gates; no paid/provider workload was run.
- Self-approval and bounded run config are preparation policy, not executed work.
  T04 adds durable operations; T05/T06 add revisions/approval/simulated deployment.
- Audit remains editable by DB administrators, although no audit-write/delete API
  exists. Account deactivation has no management API/UI. Local admin seed/bootstrap
  are direct-DB tools, not an external identity system. Legacy dependency
  deprecation warnings remain; no dependencies were added or globally installed.

## Next task

After verifying T03 is merged into updated main and inspecting its current CI,
implement **T04 — Durable operations with a separate worker** only. Create its
own task branch after inspecting Git status/prerequisites and preserving unrelated
changes. If T03 needs corrections, complete them before T04.

T04 adds operations/attempts/reservations, typed dispatch, a separately runnable
worker, idempotency, atomic claims, leases/heartbeat/fencing, retry/recovery/
cancellation and operation UI. Use an internal deterministic test handler; do not
expose arbitrary task execution. No provider submission, broker or restored RAG
job runner. Keep authorization and transactional audit/queue ownership intact.

## Files to read first

| Purpose | Files |
|---|---|
| Entry/task | `AGENTS.md`, `mdfiles/README.md`, T04 in `mdfiles/development-plan.md` |
| Worker contracts | `mdfiles/architecture.md`, `mdfiles/domain-contracts.md`, T04 rows in `mdfiles/api-contracts.md` |
| Settings/model baseline | `backend/core/config.py`, `backend/models/platform.py`, `backend/models/environment_schemas.py`, migration 006 |
| Transactions/policy | `backend/services/application_service.py`, `environment_service.py`, `policy_service.py`, `audit_service.py`, `pagination.py` |
| API | `backend/main.py`, `backend/api/dependencies.py`, `platform_errors.py`, `backend/api/endpoints/environments.py` |
| UI | `frontend/registry.py`, `registry_widgets.py`, `environment_ui.py`, `api_client.py` |
| Tests | `tests/conftest.py`, `tests/unit/test_environments.py`, `test_registry_ui.py`, `tests/integration/test_migrations.py`, `test_environment_bindings.py` |
| Setup/checks | Root README, `.env.example`, `mdfiles/testing-and-operation.md`, CI workflow, `backend/seed_sandbox.py` |

Do not read `.env` into tool output. PostgreSQL/Redis, when available, belong to
`~/code/devstack`; use isolated app/test databases and do not modify shared
configuration or other databases. Redis is not required by this platform.

## Suggested agent prompt

> Read AGENTS.md, mdfiles/README.md, and mdfiles/next-agent.md. Inspect Git status
> and verify T03 is merged into updated main, including current CI evidence.
> Implement T04 only on its own branch. Preserve unrelated changes, explain the
> plan, run acceptance checks, update the handoff and affected docs, and open a
> draft PR against main. Do not merge, start T05, run paid workloads or deploy
> infrastructure. Keep simulation explicit and worker execution durable in
> PostgreSQL. Docker builds/startup remain unverified unless newer evidence exists.
