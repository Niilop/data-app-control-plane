# Development plan and agent task ledger

Status: all tasks **not started**. This plan is implementation-ready guidance,
not a claim of implemented capabilities. Task order follows dependencies rather
than estimated calendar dates. Do not implement the entire roadmap in one turn.

## Delivery order

```text
T01 -> T02 -> T03 -> T04 -> T05 -> T06 -> T07
                                             |-> T08 -> T09 -> T10
                                             |-> T11
T07 + T09 + T11 -> T12
T10 + T12 -> T13 organizational pilot design
```

Complete T11 after T07 for the full offline demonstration, then T08–T09 for real
GitHub integration. T10 can wait for an available workspace; continue recovery
tests using scripted provider failures without pretending the real gate passed.

Every task includes documentation updates and relevant tests. Common requirements:
read [repository-map.md](repository-map.md), inspect affected code, preserve
migration history/data, and follow [testing-and-operation.md](testing-and-operation.md).
Use linked contracts for details; scope exclusions below prevent unrelated work.

## T01 — Reproducible local platform foundation

**Status:** not started. **Depends on:** none.

Deliver T01 as two reviewable branches, in order:

- **T01a — `feat/t01a-local-startup`:** optional legacy feature startup, safe local
  settings, configurable frontend API URL, isolated unit-test collection, and
  project-local Ruff/pytest/mypy tooling. Verify startup without LLM credentials.
- **T01b — `build/t01b-containers-ci`:** locked container builds, devstack/optional
  Compose database configuration, PostgreSQL migration smoke tests, and platform CI.

T01 is complete only when both blocks meet their acceptance criteria. Use a
documentation PR as the base for T01a until the documentation is merged. Rebase
later work on the merged base; do not combine unrelated roadmap tasks in one PR.

**Read:** [architecture](architecture.md), current config/main/database, workspace
pyprojects, Dockerfiles, Compose, frontend API URL, existing tests and migrations.

**Implement:** platform-local settings with legacy features opt-in; API startup
without LLM credentials; configurable frontend API URL; locked uv workflow for
local and container dependencies; Ruff, pytest, and a type checker (initial choice:
mypy) in project-local dev dependencies. Configure isolated test discovery so live
legacy scripts cannot execute during collection; preserve them as manual examples.
Document devstack database setup and an optional self-contained Compose DB profile
without colliding with its port. Add this repository's CI with offline unit checks
and an isolated PostgreSQL migration smoke test. Default SQL debug logging off.

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
Check the independently edited `uv.lock` ignore rule noted in the repository map;
resolve lockfile availability for a clean checkout without silently discarding the
user's concurrent changes.

## T02 — Register an owned application

**Status:** not started. **Depends on:** T01.

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

**Status:** not started. **Depends on:** T02.

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

**Status:** not started. **Depends on:** T03.

**Read:** worker/failure protocol in [architecture](architecture.md), operation
state/idempotency contracts, T04 API rows; legacy job runner for comparison only.

**Implement:** operations/attempts/reservations migration; typed dispatch;
independently runnable worker and Compose service; idempotency, atomic claims,
leases, heartbeat, fencing, bounded retry, cancellation/recovery APIs and operation
UI. Use an internal deterministic test handler to exercise infrastructure; do not
expose an arbitrary task-execution API. Add liveness/readiness and queue telemetry.

**Exclude:** real provider submission, message broker, rewriting legacy RAG jobs.

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

## T05 — Generate a bundle and capture a revision

**Status:** not started. **Depends on:** T04.

**Read:** [integrations](integrations.md), artifact/revision/validation contracts,
T05 API rows. Inspect only template-related new code plus worker handler patterns.

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
