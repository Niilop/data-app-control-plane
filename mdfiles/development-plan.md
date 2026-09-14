# Development plan and agent task ledger

Status: **T01–T04 complete and merged; T04a implemented, pending review/merge**.
T05 is next after T04a merges; later tasks have not started.
This plan is implementation-ready guidance,
not a claim of implemented capabilities. Task order follows dependencies rather
than estimated calendar dates. Do not implement the entire roadmap in one turn.

## Supporting change — PR handoff policy

Implemented separately from T01b: AGENTS.md now requires same-PR handoff updates;
the PR template prompts for evidence and affected docs; the `Agent handoff` workflow
checks `mdfiles/next-agent.md` against the PR merge-base diff. Non-documentation
changes require a content update and six standard sections. Documentation-only
changes are exempt from updating the handoff, but its structure must remain valid.

Verification: 18 disposable-Git-history tests passed using
`uv run --locked pytest tests/unit/test_agent_handoff.py -q`; Ruff lint/format and
`uv run --locked mypy scripts/check_agent_handoff.py` passed. Hosted CI is not
claimed as verified here. No application code changed, and the existing application
suite was not rerun for this tooling-only change. T01b remains pending.

Reviewers must check factual accuracy. Required-status enforcement needs repository
rules configured separately; this change does not alter repository permissions or
merge rules. The handoff describes proposed code state rather than merge status.

## Delivery order

```text
T01 -> T02 -> T03 -> T04 -> T04a -> T05 -> T06 -> T07
T07 -> T08 -> T09 -> T10
T07 -> T11
T07 + T09 + T11 -> T12
T10 + T12 -> T13 organizational pilot design
```

Complete review/merge of T04a before adding T05 feature screens to React. Complete T11 after T07 for the full offline
demonstration, then T08–T09 for real
GitHub integration. T10 can wait for an available workspace; continue recovery
tests using scripted provider failures without pretending the real gate passed.

Every task includes documentation updates and relevant tests. Common requirements:
read [repository-map.md](repository-map.md), inspect affected code, preserve
migration history/data, and follow [testing-and-operation.md](testing-and-operation.md).
Use linked contracts for details; scope exclusions below prevent unrelated work.

## T01 — Reproducible local platform foundation

**Status:** complete. T01a and T01b are both merged into `main` (T01b via PR #5,
merge commit `07e90c5`). Hosted CI confirmed the isolated PostgreSQL migration
tests pass for real at `a50795c` (3 passed, no skips). Docker builds and bundled
Compose startup were subsequently verified during the T04 follow-up; see
`mdfiles/next-agent.md`. The T01b notes below retain their original test scope. **Depends on:** none.

Deliver T01 as two reviewable branches, in order:

- **T01a — `feat/t01a-local-startup`:** removal of AI features, safe local
  settings, configurable frontend API URL, isolated unit-test collection, and
  project-local Ruff/pytest/mypy tooling. Verify startup without LLM credentials.
- **T01b — `build/t01b-containers-ci`:** locked container builds, devstack/optional
  Compose database configuration, PostgreSQL migration smoke tests, and platform CI.

T01 is complete only when both blocks meet their acceptance criteria. PRs #1 and
#2 are merged into main at `fd28d94`, including follow-up Compose DB-name fix
`f1e4381`. T01b starts from merged main on `build/t01b-containers-ci`; do not combine
unrelated roadmap tasks in one PR. See [the next-agent handoff](next-agent.md).

**Read:** [architecture](architecture.md), current config/main/database, workspace
pyprojects, Dockerfiles, Compose, frontend API URL, existing tests and migrations.

**Implement:** platform-local settings with AI features removed; API startup
without LLM credentials; configurable frontend API URL; locked uv workflow for
local and container dependencies; Ruff, pytest, and a type checker (initial choice:
mypy) in project-local dev dependencies. Configure isolated test discovery so live
legacy scripts cannot execute during collection; preserve relevant auth/example
scripts as manual examples and remove obsolete AI scripts.
Document devstack database setup and an optional self-contained Compose DB profile
without colliding with its port. Add this repository's CI with offline unit checks
and an isolated PostgreSQL migration smoke test. Default SQL debug logging off.

User clarification: remove AI chat, RAG, LLM, and inference code fully instead of
keeping a legacy-mode toggle. Preserve historical tables and migration metadata.

Do not install globals, upgrade every legacy library, rewrite import paths, drop
tables, or implement the worker/domain. Keep legacy migrations working, including
their pgvector requirement. Make new-code checks scoped explicitly rather than
ignoring new errors or requiring unrelated legacy cleanup.

**Acceptance:**

- From a clean locked environment with only DB/development-auth configuration,
  platform API starts and `/health` responds with no LLM keys or provider calls.
- Default route assembly does not import/initialize legacy LLM services.
- Test collection makes no HTTP requests and runs without a live API/provider.
- Empty isolated PostgreSQL database migrates through existing head; metadata
  imports work with LLM features disabled.
- Backend/frontend image builds use the uv lock; local and container API URLs
  are documented. Do not print secrets through resolved Compose configuration.
- Ruff, focused type checking, and foundation tests pass locally or are explicitly
  recorded as blocked by unavailable dependencies/DB. CI configuration alone is
  not proof that a hosted CI run passed.

**Handoff:** exact commands, dependency/tool versions, local DB setup, test baseline,
files changed, unrun checks. Update the root README to link this plan and describe
actual startup; preserve legacy usage notes where needed.
`uv.lock`, `AGENTS.md`, and `mdfiles/` are deliberately tracked. The post-merge
context handoff resolves the earlier `.gitignore`/local-only AGENTS uncertainty.
Preserve any new unrelated local edits when committing this task.

### T01a handoff — 2026-09-11

- **Status:** complete and merged through PR #2, then PR #1 into main. Original
  branch: `feat/t01a-local-startup`, based on `docs/platform-development-plan`.
  T01b remains a separate next PR against main.
- **Implemented:** AI/chat/RAG/inference services, routes, UI, configuration, and
  dependencies removed per user clarification; RAG-only job runner removed.
  Local API exposes auth/system routes with SQL debug off. UI provides account
  controls and health/profile checks with configured API URL and timeouts.
- **Persistence:** migration versions unchanged. Historical feature metadata moved
  to `backend/alembic/legacy_models.py`; no table/data deletion. Retained the
  `EMBEDDING_DIM` compatibility constant imported by migration 002. Removed local
  Alembic package marker that shadowed the installed package.
- **Verification:** `uv sync --locked --all-packages --group dev --offline` passed
  after initial dependency download. Python 3.11.16, uv 0.12.11, pytest 9.1.1,
  Ruff 0.16.7, mypy 2.3.1. `uv run --locked pytest -q`: **17 passed**.
  Collection finds only those 17 offline tests. Ruff lint/format passed for all
  new/modified nonhistorical implementation files and new tests; mypy passed for
  settings and API assembly. Exact commands are in the root README.
- **Environment note:** Starlette TestClient stalled inside the execution sandbox;
  the suite passed outside it, retaining explicit outbound-network guards.
- **Not run:** live PostgreSQL migrations, real login against DB, Docker image
  builds, hosted CI, GitHub/Databricks workload execution. No claim of those gates.
- **Next:** T01b locked container builds + devstack/optional DB Compose + isolated
  PostgreSQL migration smoke + CI. CSV/example modules remain dormant; new platform
  domain features start at T02 after T01b. Keep user `.gitignore` changes separate.

### T01b handoff — 2026-09-11

- **Status:** implemented on `build/t01b-containers-ci` (fast-forwarded from
  merged main at `f4ab415`, which includes PR #4), opened as PR #5, and
  **merged into `main`** as merge commit `07e90c5`. T02 not started; no cloud
  resources touched.
- **Implemented:** uv-locked, pinned (`0.12.11`) multi-stage backend/frontend
  Dockerfiles (venv at `/opt/venv`, outside the Compose dev bind mount); a root
  `.dockerignore`; the bundled Compose `db` service moved behind an opt-in
  `local-db` profile with a configurable host port (default `5433`) and a
  non-blocking `depends_on`, plus `host.docker.internal` for reaching devstack
  from a container; isolated PostgreSQL+pgvector migration integration tests
  (`tests/integration/test_migrations.py`, marked `integration`, schema-isolated,
  gated on `TEST_DATABASE_URL`, skipped with a visible reason when unset); the
  offline network guard in `tests/conftest.py` scoped to skip `integration`-marked
  tests; a new `.github/workflows/ci.yml` with a locked lint/type/offline-test job
  and an isolated migration job backed by a `pgvector/pgvector` service container;
  two real bug fixes in `backend/alembic/env.py` found via hosted CI (a
  `configparser` percent-escaping issue on `sqlalchemy.url`, and a
  `Base.metadata` duplicate-table registration when a process calls
  `command.upgrade()` more than once). `.github/workflows/agent-handoff.yml` is
  unchanged.
- **Verified locally:** `uv sync --locked --all-packages --group dev`, `uv run
  --locked pytest -q` (**37 passed**, up from T01a's 17), `uv run --locked
  mypy` (clean), `uv run --locked ruff check`/`ruff format --check` over the
  documented scope plus `tests/integration` (clean).
- **Verified by hosted CI:** [Platform CI run 34608464924](https://github.com/Niilop/data-app-control-plane/actions/runs/34608464924)
  passed both jobs at PR head `a50795c`. The
  [`postgres-migration` log](https://github.com/Niilop/data-app-control-plane/actions/runs/34608464924/job/103292661662)
  reports **3 passed in 1.47s** against `pgvector/pgvector:pg16` — no skips —
  confirming both `env.py` fixes for real, including repeated upgrades and
  data preservation across a revision. The `lint-type-offline-tests` job and
  the `agent-handoff` check also passed.
- **Not verified:** Docker image builds, `docker compose up`, and any live
  startup/health smoke check through the containers — no environment involved
  in T01b (implementation or CI) had a working Docker daemon. Devstack
  integration specifically (whether its actual Postgres port/credentials match
  what's documented) is also unverified — no devstack checkout was available.
- **Full details:** see `mdfiles/next-agent.md`.

## T02 — Register an owned application

**Status:** complete and merged via PR #6 at `712aa25` on 2026-09-11.
**Depends on:** T01 (merged at `07e90c5`). Merge confirmed through GitHub and
ancestry of T02 head `fa8b7f4` in updated `origin/main`.

**Implemented:** migration `005_owned_applications`; active/admin user flags with
safe defaults for legacy users; new teams, memberships, applications, direct/team
roles and audit tables. Central current-actor/policy checks; API create/list/detail,
versioned metadata/ownership updates, membership/role management and paginated
history. Explicit local account bootstrap prompts for passwords and audits admin
intent; public registration rejects privilege fields. Streamlit supports the full
registration/detail/history flow and minimal team/role administration. GitHub
references remain unverified. No external permissions or infrastructure changed.

**Verification:** 67 offline tests passed, including API policy/rollback cases and
Streamlit workflows through the in-process API. Mypy passed for 18 platform files.
The PostgreSQL suite was exercised locally only for its skip path: 6 skipped with
`TEST_DATABASE_URL` unset. It now covers old-head user preservation/defaults,
new-model/schema parity, constraints, API rollback, and simultaneous versioned
updates in addition to the original chain tests. [Hosted Platform CI run 34615449895](https://github.com/Niilop/data-app-control-plane/actions/runs/34615449895)
passed at `77a9a03`: actual logs report **6 PostgreSQL tests passed**, no skips,
**67 offline tests passed**, Ruff and mypy clean. The handoff check also passed.
Exact evidence and limitations are recorded in [next-agent.md](next-agent.md). Docker's launcher reports WSL integration unavailable.

**Next:** T03 only, when assigned, on its own branch from updated main. Existing T01b Docker
build/startup verification remains outstanding.

**Read:** [domain contracts](domain-contracts.md), T02 rows in
[API contracts](api-contracts.md), current auth/router/model files.

**Implement:** user-active/admin support, teams/memberships, applications,
application-role assignments, centralized actor/policy dependency, transactional
audit, new migration. Provide explicit local bootstrap/demo accounts with no
committed/default production passwords. Add application register/list/detail UI
and minimal admin team/role controls. Implement permission-filtered pagination,
optimistic metadata updates, request IDs and platform error envelopes.

**Exclude:** repository network verification, environments, worker, approvals,
external identity/groups/permissions. Owner/data owner do not grant infrastructure
rights. Keep existing login compatible for local development.

**Acceptance:**

- An authorized team member registers an application; ID, accountable people,
  repository reference, and initial roles persist and appear in UI/history.
- Duplicate slug, invalid URL/path, unknown owner/team, and stale metadata version
  fail predictably. Repository is visibly unverified.
- Unauthorized users cannot read another application's detail/list/audit or assign
  roles; nonadmin registration cannot select admin privileges.
- A transaction failure leaves neither a partial application nor a success audit
  event. Membership changes and metadata changes have attributable audit records.
- Fresh migration and upgrade from old head succeed without losing legacy users.

## T03 — Register a sandbox environment binding

**Status:** complete and merged (PR #8, `46a9cd9`). **Depends on:** T02 (merged).
Started from updated main `928f2f7`, including the merged T02 handoff PR #7.

**Implemented:** migration 006 adds versioned environments and unique application/
environment bindings. Admin-only writes; permission-filtered environment/binding
reads; explicit local simulated references/executor, approved bundle targets,
enabled and self-approval policies, closed versioned integer configuration.
Environment changes lock against binding writes and bump/audit all affected binding
versions atomically. Streamlit supports environment creation/policy and binding
create/edit/read. An explicit idempotent local seed requires an active admin.
Startup requires `DEPLOYMENT_EXECUTOR=simulated` and rejects unsupported profiles,
real executors and mismatches; existing local `.env` files need this opt-in.

**Verification:** 108 offline tests passed, including API/UI authorization, target/
config validation, stale edits, seed behavior and rollback. Ruff checks passed over
the T03 scope and mypy passed for 24 source files. Local PostgreSQL execution
reports ten skips with `TEST_DATABASE_URL` unset. Hosted
[Platform CI run 34624002359](https://github.com/Niilop/data-app-control-plane/actions/runs/34624002359)
at `974c16e` passed: actual logs report **10 PostgreSQL tests passed**, no skips,
**108 offline tests passed**, Ruff and mypy clean. Agent handoff also passed.
Exact evidence is in `next-agent.md`; local skips alone prove no database behavior. Docker builds/live startup remain unverified. No real environment was
seeded and no provider or paid workload was run.

**Merge confirmed:** T03 PR #8 merged at `46a9cd9`. T04 proceeds from that updated main.

**Read:** profile section in [architecture](architecture.md), binding/policy
invariants in [domain contracts](domain-contracts.md), T03 API rows.

**Implement:** admin environment/binding models, migration, API and UI; simulated
sandbox seed/configuration; explicit self-approval setting; versioned safe config.
Credential values are not accepted in registry payloads. Reject unsupported
organization mode and mismatched execution profiles at startup.

**Exclude:** workspace creation, Terraform, connectivity validation, deployment.

**Acceptance:** admin can bind an application once per environment; duplicate,
unapproved target, secret-bearing/unknown config, and unauthorized edits fail;
returned records contain no credentials; local demo needs no external account;
configuration changes increment binding version and are audited.

## T04 — Durable operations with a separate worker

**Status:** PR #9 confirmed merged as `9a36e56aac10a3b8c87cafbdc0f75f85b7752ff1`.
**Depends on:** T03 (merged).

**Delivered:** migration 007 queue/attempt/reservation/probe/command/heartbeat tables;
transactional enqueue/audit and scoped idempotency; PostgreSQL claims, leases,
heartbeats, fencing and separate worker/Compose service; fixed simulated handler;
bounded retry, cancellation and operator recovery; authorized API/UI history and
freshness; API liveness/readiness and admin queue telemetry. No generic task API.

**Verification:** 126 offline tests passed, Ruff clean (53 files), mypy clean
(32 files). Local integration collection reports 15 explicit skips. Hosted
[Platform CI run 34632237191](https://github.com/Niilop/data-app-control-plane/actions/runs/34632237191)
at `d1c417d` passed: actual logs confirm **15 PostgreSQL tests passed**, no skips,
**126 offline tests passed**, Ruff and mypy clean. Exact results are in `next-agent.md`.
PostgreSQL tests cover separate competing processes, API/worker restart recovery,
stale fencing, concurrent submissions, heartbeat/cancel, migration round trip and
transaction rollback. Do not treat local SQLite checks or integration skips as
proof of PostgreSQL behavior. A subsequent local Docker follow-up passed all
image builds, quiet Compose validation, bundled database startup, fresh migration
through 007, API liveness/readiness and Streamlit health. The earlier I/O error
was confined to the agent session's Docker CLI mount; regular Ubuntu could reach
Docker Desktop. First-start migration/configuration steps are documented in root
README. Devstack integration and the interactive account journey remain unverified.

**Next:** T04a is implemented below and awaits review/merge; T05 follows.

**Read:** worker/failure protocol in [architecture](architecture.md), operation
state/idempotency contracts, T04 API rows; the operation contract; the old RAG job runner has been removed.

**Implement:** operations/attempts/reservations migration; typed dispatch;
independently runnable worker and Compose service; idempotency, atomic claims,
leases, heartbeat, fencing, bounded retry, cancellation/recovery APIs and operation
UI. Use an internal deterministic test handler to exercise infrastructure; do not
expose an arbitrary task-execution API. Add liveness/readiness and queue telemetry.

**Exclude:** real provider submission, message broker, reintroducing removed RAG jobs.

**Acceptance:**

- Persisted operation survives API and worker restart and completes after reclaim.
- Two worker processes cannot own the same valid lease. After forced expiry, an
  old token cannot write results, including related resource state.
- Same idempotency key/payload returns one operation; changed payload returns 409.
- Request state, operation, and audit are atomic under injected transaction failure.
- Safe transient failures back off to the configured limit; terminal failures stop.
- Cancellation before claim prevents handler execution; running cancellation shows
  intent until observed. Unknown outcomes retain conflict reservations.
- A status/attempt page exposes useful sanitized diagnostics and freshness.

## T04a — Replace Streamlit with React

**Status:** implemented, pending review/merge. **Depends on:** T04 (merged).

**Delivered:** clean light React/TypeScript/Vite interface for accounts, applications,
ownership/roles, teams/memberships, environments/bindings, audit and operation
history/recovery. Native dialogs restore keyboard focus; responsive navigation and
paginated tables/selectors preserve usable narrow layouts. Forms retain original
versions; current API capabilities control affordances without replacing policy.
Browser login uses HTTP-only cookies with origin/custom-header write checks;
bearer API clients remain compatible. Docker now serves static React assets and
same-origin API routes through nginx on 8501. Streamlit runtime, workspace member,
dependencies and UI-only tests were retired after browser parity passed. Existing
accounts, data and migrations are preserved. ADR-016 records the session/runtime
choices. Frontend checks and production-proxy smoke are included in CI.

**Verification:** 125 offline Python tests passed; Ruff lint/format clean across
48 files; mypy passed for 28 platform files. Locked frontend install, lint,
format, type checks and production build passed; 9 real Chromium workflows passed
using a disposable FastAPI/SQLite API and simulated worker fixtures. Desktop and
390px mobile screenshots were inspected. All Compose images built, four local
services started, and `/ready` through nginx returned ready. An isolated production
nginx browser smoke passed routing, CSP, login, cookie reload, an authenticated
write, readiness and logout. Browser assets contain no configured server secrets
or test credentials. Hosted
[Platform CI run 34649546595](https://github.com/Niilop/data-app-control-plane/actions/runs/34649546595)
passed at `7cb2c20`: actual logs confirm **125 offline**, **15 PostgreSQL** (no skips),
**9 browser** tests and production nginx smoke, with all lint/type/build checks.
The delayed-response regression verifies that versioned edit controls wait for
fresh records after refresh. PostgreSQL integration tests were not rerun locally.
The final follow-up only records verification in docs; no local application rerun
was needed for it. Recheck current CI before merge.


**Decision:** [ADR-015](decisions.md#adr-015--replace-streamlit-before-t05).

**Read:** current frontend modules and UI tests in [repository map](repository-map.md),
[API contracts](api-contracts.md), role/version/idempotency rules in
[domain contracts](domain-contracts.md), [architecture](architecture.md), and the
local container/verification instructions in root README.

**Implement:** a React + TypeScript frontend built with Vite, covering the existing
T01–T04 workflows. Design a consistent navigation/layout, application list/detail,
forms, status indicators, loading/empty/error states and accessible controls.
Preserve the FastAPI/service/worker boundary, existing accounts, database data,
permissions and audit history. Add only small, authorized API improvements needed
by these workflows, such as selectors; document and test any new API contract.

Build the new UI alongside Streamlit during migration. First establish routing,
API access and browser login/session handling, then complete login -> application
list -> registration -> detail/edit. Migrate teams/memberships, ownership/roles,
environments/bindings, audit history and operation status/attempts/recovery next.
Keep the current registration, logout and profile behavior available. Handle
expired sessions deliberately; browser token/session storage must be reviewed,
not copied mechanically from Streamlit's server-side session state. Keep database
credentials and server signing keys out of browser bundles and frontend config.

Add a project-local Node toolchain, committed package lock, frontend lint/type/build
checks and browser workflow tests. Keep uv for Python; select and pin the frontend
toolchain and supporting libraries during implementation. Update Docker/Compose
and startup docs to serve the new frontend and route API requests consistently.
Once current workflows are verified in the replacement, remove Streamlit runtime,
its dependencies and Streamlit-specific tests; retain equivalent behavior coverage
and the backend suites. Update the Python lock if removing the frontend workspace
member or its dependencies. Do not leave two permanent UI implementations.

**Exclude:** T05 generation/artifact/revision features, approvals/deployments, real
providers, organization identity/SSO redesign, backend business-rule rewrites,
marketing pages or speculative dashboards. Keep the initial visual scope to the
current application. Do not expand Streamlit with new feature screens.

**Acceptance:**

- Existing accounts can sign in, view their profile and sign out; expired sessions
  are handled predictably. No account/database reset is required for the cutover.
- Browser tests exercise registration/list/detail/edit and administration of
  teams, roles, environments and bindings against the real local/test API.
- Visibility/denied actions, stale-version conflicts, validation errors, pagination,
  simulation labels, audit history and idempotent operation recovery remain correct.
  The API remains authoritative for authorization, including revoked grants.
- Operation status/attempt history exposes observation freshness and supports
  refresh/cancel/retry/reconcile without duplicate submissions on request retry.
- Navigation, forms and status feedback work with keyboard access and at common
  desktop and narrower viewport sizes. Loading, empty and API failure states are usable.
- Locked frontend install, lint/type checks, production build and browser tests
  pass; applicable backend checks remain green. Compose builds and serves the
  replacement with working login/API access and worker readiness.
- Streamlit runtime/dependencies/tests are retired only after equivalent workflows
  pass. Root README, handoff and repository map describe the resulting toolchains
  and launch commands; no server secrets appear in generated browser assets.

**Next:** after T04a is reviewed and merged, resume T05 using the React frontend.

## T05 — Generate a bundle and capture a revision

**Status:** implemented on `feat/t05-bundle-generation`, pending review/merge.
**Depends on:** T04a (frontend) and T04 (worker), both merged.

**Evidence:** hosted [Platform CI run 34657096948](https://github.com/Niilop/data-app-control-plane/actions/runs/34657096948)
passed at `44484ee`: 188 offline tests (63 new), 23 isolated PostgreSQL tests (8 new),
11 Chromium browser workflows (2 new), the production nginx smoke, Ruff/mypy, and
`scripts/check_generated_project.py` proving the generated project installs from
its own lock and passes its own tests with `uv --offline`. Local Docker Compose
was migrated to head 008 with existing accounts preserved, and the artifact mount
was confirmed shared between the API and worker containers. See `next-agent.md`
for exact counts and what was not run. See ADR-017 for the decisions taken.
The 2026-09-14 review follow-up moves generation and validation replay handling
after current visibility/developer authorization and adds two revocation
regressions; `uv run --locked pytest -q` passed locally with **190 tests**, and
focused Ruff plus full mypy passed. Hosted CI for the follow-up was not run locally.

**Read:** [integrations](integrations.md), artifact/revision/validation contracts,
T05 API rows. Inspect template-related code, worker handler patterns and the
React frontend established in T04a. Add all new feature screens there.

**Implement:** one versioned Python batch template with synthetic input and unit
tests; deterministic safe archive generator; local artifact adapter with digest
verification; generation operation/download UI; immutable revision snapshots and
offline validation operation/report. Select supported template dependency/tool
versions during implementation, then lock them. Label offline checks precisely.

**Exclude:** writing/publishing Git repositories, real bundle deployment, external
validation, executing arbitrary adopted repository code in the general worker.

**Acceptance:** same approved template/inputs yield same digest; invalid names,
path traversal, unsafe archive entries, secret parameters, and digest mismatch are
rejected. Download requires application access. Generated project installs from
its lock and passes its own tests in an isolated test environment. Generation
itself requires no network. Revision source/config cannot be edited; a new input
creates a new revision. Simulated/offline validation is never labelled workspace
validation. API restart does not lose artifacts in the configured shared mount.

## T06 — Approve and simulate one deployment

**Status:** not started. **Depends on:** T05.

**Read:** approval/permission/state contracts and [integration trust boundary](integrations.md).

**Implement:** approval/deployment migration and endpoints; approval screen;
simulation executor; transactionally submitted deployment; conflict reservation;
worker authorization/approval recheck; deployment history and last-success view.
Use the initial combined developer/operator submission rule from domain contracts.

**Exclude:** GitHub, Databricks calls, external permission grants, enterprise gate.

**Acceptance:** complete generate -> validate -> approve -> simulated deploy in UI;
exact source/config/target/validation scope is visible. Wrong approval scope,
binding change, archived/inactive target, missing role, revoked approver, and
disallowed self-approval block execution. Local self-approval is explicit/audited.
Duplicate requests yield one deployment; conflicting requests fail atomically.
Simulated partial failure preserves resource observations and prior successful
deployment. Every deployment/result shows `execution_mode=simulated`.

## T07 — Run a simulated job and inspect the application

**Status:** not started. **Depends on:** T06.

**Read:** JobRun model/state and T07 API/UI contracts.

**Implement:** allowlisted job run operation, simulated run adapter behavior,
run records and application dashboard containing revision, approval, deployment,
run result, operation history, and observation time. Support deterministic
simulated success/failure fixtures without letting arbitrary users choose a fake
outcome for real mode.

**Exclude:** arbitrary script execution, scheduling, real compute.

**Acceptance:** authorized operator runs a job from a successful deployment;
unknown job, invalid parameters, inaccessible/failed deployment, and unauthorized
caller are rejected. Run status is independent from deployment status, simulation
is explicit, and all reads use recorded DB state. API response does not leak
credentials or local storage paths.

## T08 — Adopt an existing GitHub repository and run CI

**Status:** not started. **Depends on:** T07.

**Read:** source-capture/CI sections in [integrations](integrations.md), T08 API rows.

**Implement:** GitHub repository adapter; asynchronous verification/source capture;
resolve branch/ref to immutable commit; inspect approved bundle root without
executing code; associate CI observations with exact commit. Add generated PR CI
workflow and onboarding instructions. Manually applying reviewed generated files
is sufficient; no repository-write automation is required. UI shows CI/source
verification and failed adoption diagnostics.

**Exclude:** repo creation, automatic commits/PRs, deployment credentials, data jobs.

**Acceptance:** mocked API tests cover missing/private repos, invalid credentials,
pagination, rate limits, moving refs, and malformed archives. Captured commit is
unchanged when branch moves. No arbitrary URL fetching or source execution in
worker. With separate authorization, demonstrate one genuine GitHub CI run on
the generated project's commit; if unavailable, record real gate as pending.

## T09 — Dispatch and reconcile a harmless GitHub workflow

**Status:** not started. **Depends on:** T08.

**Read:** outbound polling, correlation, manifest and trust sections in
[integrations](integrations.md); lease/concurrency contracts.

**Implement:** GitHub executor adapter with trusted workflow selection,
correlation persisted before dispatch, polling, cancellation, result validation,
rerun-attempt identity, and `needs_attention` recovery. Start with a workflow that
checks the source/manifest and performs no Databricks deployment. Mark this a
workflow probe; it must not mark a deployment as successful.

**Exclude:** real Databricks identity, paid jobs, claims of enterprise approval enforcement.

**Acceptance:** worker triggers a matching probe and records genuine run ID/result
without inbound callbacks when explicitly authorized. Scripted tests cover lost
dispatch response, delayed run visibility, duplicate matches, mismatched commit or
manifest, API outage, restart, and cancellation race. No ambiguous dispatch is
blindly repeated, stale worker cannot release the reservation, and unrelated
latest runs are never misattributed. Credentials do not appear in logs/API/DB payloads.

## T10 — Real Databricks sandbox deployment and job

**Status:** not started. **Depends on:** T09.

**External prerequisites:** an existing authorized workspace, supported compute,
reviewed limited identity, cost/timeout configuration, and explicit user permission
to activate execution. Lack of these blocks this integration gate only.

**Read:** full [integration contract](integrations.md), ADR-005/007/008 in
[decisions](decisions.md). Verify current Azure Databricks docs for the actual account.

**Implement:** trusted workflow validates/deploys exact captured source/config and
publishes genuine deployment references; restricted Databricks run submit/observe
adapter; synthetic job output check and UI. Prefer tested federation where available.
Recheck approval before dispatch and document single-admin trust limits. Implement
safe run reconciliation using provider-supported identifiers/idempotency where
available; uncertainty must stop automatic resubmission.

**Exclude:** production, workspace provisioning, broad ACL/data grants, scheduled
compute, declaring organizational approval enforceable from the local DB alone.

**Acceptance:** one approved revision deploys to the registered target and records
real external resource IDs; one small job terminates and produces verified output.
No branch drift, wrong target, offline-only validation claim, or silent simulation
fallback. Record actual workflow/run links, tool versions, elapsed time, applicable
cost observations, and resource stop/cleanup instructions. Code can be complete
while the real execution gate remains pending; state both explicitly.

## T11 — Platform access requests, revocation, and archive

**Status:** not started. **Depends on:** T07. Can precede T08.

**Read:** persona/permission distinctions, AccessRequest and archive contracts,
T11 API rows and existing role/operation services.

**Implement:** own-access request and owner/admin decision UI; transactional role
grant, explicit role revocation with effective-access explanation; archive flow.
Use T02 membership/assignment primitives; do not create a second permission system.

**Exclude:** directory groups, Git collaborators, Databricks ACLs, data grants,
external resource deletion.

**Acceptance:** requester cannot approve their own request unless independently
authorized by explicit owner/admin role; duplicate approval cannot duplicate grant.
Unauthorized users see only their own request outcome, not private application
metadata. Revoke every effective grant and demonstrate API denial and blocked
queued execution. If another team grant remains, UI shows retained access.
Archive rejects unresolved work, blocks new commands, and preserves data/history.

## T12 — Recovery and measured workload evidence

**Status:** not started. **Depends on:** T07, T09, T11; real T10 tests optional until available.

**Read:** [testing and operation](testing-and-operation.md), reliability contracts.

**Implement:** deterministic fault scenarios and a repeatable demo/load harness;
record measured results in `mdfiles/verification-report.md` when measurements exist.
Declare machine, workload, sample count, and targets before running. Start with
10 simulated applications, 2 worker processes, 100 accepted operations across
nonconflicting bindings, plus a conflicting-request batch. Choose/revise latency
targets from an initial baseline; do not invent a production SLA.

**Acceptance:** measure API p50/p95, queue age, throughput, contention, retry count,
restart recovery, and cancellation delay. Prove duplicate-request handling,
stale-worker rejection, uncertain-dispatch reconciliation, authorization revocation,
and same-binding serialization. Rehearse isolated DB restore and artifact recovery.
List unsupported or untested scenarios; simulations do not satisfy real-provider evidence.

## T13 — Organizational pilot design gate (optional later work)

**Status:** not started. **Depends on:** T10, T12; company-specific requirements.

**Implement in this task:** a reviewed design/acceptance checklist for one team's
pilot covering external identity/group mapping, true deployment approval
enforcement, restricted execution, shared artifact migration, backup/restore,
audit retention, telemetry, cost ownership, and access revocation. Choose actual
hosting/provider features based on company constraints. Resolve ADR-007 before
creating implementation tasks for privileged deployment paths.

**Exclude:** automatic cloud deployment, a generic enterprise framework, implementing
every directory/CI/infrastructure provider. Do not claim profile selection alone
creates organizational readiness.

**Acceptance:** concrete trust model, permission matrix, operational owner,
migration/rollback plan, and executable pilot tests are reviewed; follow-up tasks
are bounded and separately authorized. Real deployment requires independent review.

## Agent assignment template

```text
Implement TXX from mdfiles/development-plan.md only.
Read AGENTS.md, mdfiles/README.md, and the task's context links.
Confirm its dependencies against implementation and recorded evidence.
Inspect affected source; explain the multi-file plan; implement the slice.
Honor exclusions and do not activate external/potentially paid work without
existing task-specific authorization. Continue all independent local work.
Run relevant checks and update the task handoff and affected contracts.
Do not mark completion based only on code generation or mocked external tests.
```

## Handoff template

Append under the completed/in-progress task; replace its status above:

```text
Status: not started | in progress | blocked | complete
Date:
Implemented behavior:
Files / migration IDs:
Checks run and results:
Checks not run and why:
External gate: not applicable | pending | verified (evidence)
Contract/decision changes:
Known limitations and blockers:
Next task / exact resume point:
```

Task completion requires its applicable acceptance criteria. Track local code
completion separately from external verification; preserve pending external gates.
