# Architecture decisions and open gates

Recorded 2026-09-11. “Accepted direction” reflects user choices; “provisional” is
an implementation default that can change with evidence. When changing a decision,
retain its history, rationale, affected contracts/tasks, and replacement decision.

## ADR-001 — Local-first modular monolith

**Accepted direction.** FastAPI + independently runnable worker + PostgreSQL,
Streamlit for initial UI, shared business services. Local hosting supports a
single developer with essentially no cloud budget. Organizational hosting later
does not require replacing core workflows. No microservices, Azure hosting,
message broker, or Redis dependency initially. The initial Streamlit choice is
superseded for future frontend development by ADR-015; the backend direction remains.

## ADR-002 — GitHub and GitHub Actions first

**Accepted direction.** Existing GitHub repositories are onboarded; generated
projects include CI/CD definitions. GitHub Actions executes the first real
deployment workflow. The local worker dispatches/polls outbound, so no public API
or tunnel is needed. Repository creation and automated onboarding PRs are deferred.

## ADR-003 — Preserve template history; isolate new domain

**Provisional, recommended.** Keep existing users/tables/migrations and create separate platform entities.
User clarification during T01a: remove AI chat/RAG/LLM/inference features fully,
including runtime models, routes, services, UI, settings, and dependencies. Retain
historical ORM metadata under Alembic so autogeneration preserves stored data.
This supersedes the original proposal to keep AI features behind a toggle.
Do not force application/revision/operation semantics into old Pipeline/BackgroundJob.
Retain synchronous SQLAlchemy and current import layout initially. Consequence:
pgvector remains necessary for historical migrations; local
startup must still be independent of LLM credentials.

## ADR-004 — PostgreSQL durable queue

**Provisional, recommended.** Operations and related business state are inserted
atomically. Leases, fencing, stable correlation, conflict reservations, and explicit
reconciliation handle at-least-once execution. No external broker/outbox until
needed; dispatching external workflows still needs uncertainty handling. Database
fencing cannot prevent an external action already started by an old worker.

## ADR-005 — One application type and executor per environment

**Provisional.** First template is a Python batch job with synthetic data, one
bundle root per application. Local executor is explicitly simulated; real sandbox
deployment executor is GitHub Actions. A harmless workflow probe proves dispatch,
not a successful Databricks deployment. Job runs are separate from deployments.
Optional future direct CLI deployment must use the same contracts and explicit
environment selection, never race the CI executor.

## ADR-006 — Platform permissions first

**Accepted direction with provisional scope.** Build teams, application roles,
ownership, access requests, approval and revocation first. Data ownership is an
accountability field. Directory, Git, Databricks-resource and data permissions are
distinct future integrations; never imply platform membership already applies
those external grants. Local self-approval is explicit; independent approval is
required for the organizational target. Combined developer/operator deployment
submission keeps the first API small; separate role handoff can be added later.

## ADR-007 — Organizational deployment approval enforcement

**Open; blocks organizational pilot, not local development.** Local approval plus
worker checks cannot stop a GitHub/workspace administrator with an alternate
credential path. The single-admin sandbox documents that trust assumption.

Before a pilot, select enforceable approval evidence and trusted execution control
for the actual company/GitHub plan. Evaluate a centrally controlled deployment
workflow and protected immutable deployment requests, with exact-scope verification
before identity acquisition. Specify workflow edit controls, independent approval,
replay prevention, revocation, reruns, alternate dispatch paths, and audit evidence.
Add bypass tests. Do not implement ad hoc cryptographic tickets or assume paid
environment protection features without a reviewed design and actual requirements.

## ADR-008 — Real workspace and cost choices

**Open; blocks real execution only.** No workspace, compute entitlement, repository
visibility, Actions allowance, or cloud budget is assumed. Verify actual provider
limits/pricing and supported Azure Databricks authentication/compute during T10.
Prepare code locally first; activate externally only with explicit authorization.
Prefer federation when supported and reviewed. No scheduled workloads or production
data for the first demonstration. Do not promise the real path is free.

## ADR-009 — Immutable source and approval scope

**Provisional, required invariant.** Revision captures commit/artifact, template
contract/provenance, binding/config snapshots, target, and requester. Approval binds
these plus validation evidence, mode, and policy. Changes require renewed approval.
GitHub workflow ref and application source commit are separate; a moving ref is
never the approved source identity. Artifact normalization/hash is specified and
tested by T05; future build artifacts must be captured before approval when used.

## ADR-010 — Shared operation logic, explicit integration capability

**Accepted direction.** Select adapters at startup and keep provider credentials
outside payloads. Implement interfaces only as concrete integrations arrive.
Unsupported organization mode fails closed rather than pretending to be available.
Switching profiles neither migrates artifacts/data nor provisions resources.

## ADR-011 — T01b container/CI approach

**Accepted direction (T01b), 2026-09-11.** Backend/frontend images build in two
stages: a builder that runs `uv sync --locked --package <backend|frontend>
--no-dev` using the pinned `ghcr.io/astral-sh/uv:0.12.11` binary, and a runtime
stage that copies only the resulting venv (to `/opt/venv`, outside `/app`, so it
survives the Compose dev bind mount) plus that member's source. uv workspace
resolution needs every member's `pyproject.toml` present even when syncing one
package, so both are copied into the build context; only the selected member's
source is copied into the final image.

The bundled Compose `db` service sits behind an opt-in `local-db` profile with a
configurable host port (default 5433) instead of always running on 5432, so it
is never a mandatory dependency and cannot collide with devstack's PostgreSQL.
`backend`'s `depends_on: db` uses `required: false` (Compose Specification) so
startup does not block when the profile is inactive. A `host.docker.internal`
gateway mapping lets a containerized backend reach a devstack PostgreSQL
published on the host without hardcoding a network name devstack does not
publish to this repository.

Isolated PostgreSQL integration tests use a uniquely named, disposable **schema**
per test (via `TEST_DATABASE_URL`, with `search_path` scoped through the
connection's `options`), not a freshly created database, so the test role only
needs ordinary schema privileges rather than `CREATEDB`. pgvector's extension is
relocatable, so `CREATE EXTENSION IF NOT EXISTS vector` in migration 002 resolves
correctly whether it already exists in `public` or gets created in the isolated
schema. This is unverified against a real pgvector server in this sandbox (no
local Postgres/Docker); CI's `pgvector/pgvector` service container is the first
real exercise of it — treat that job's actual result as the evidence, not this
description.

## ADR-012 — T02 registry and local authorization

**Accepted implementation direction (T02), 2026-09-11.** Add separate UUID
registry tables and extend historical integer users with active/admin booleans.
Migration 005 retains users and grants no admin privileges by default. Adopt
SQLAlchemy's typed declarative base for new mapped models without changing the
synchronous engine/session or dormant table contracts.

Resolve actor and role membership from the database on every request. Team
ownership itself does not grant access: creators get direct developer/viewer,
accountable users get read access, and explicit direct/team assignments union.
Admins must join the owning team before registering; metadata editing requires
developer, while ownership/role administration requires owner/admin. No external
permission grant follows from these local roles.

Application services commit each command and audit once, rolling back failures.
Optimistic updates use a database version predicate, not just an in-memory check.
History, roles, teams and applications use scoped validated keyset cursors with
permission filtering before the limit. Server-generated request UUIDs correlate
responses and audit; errors omit request values and database diagnostics.

Local bootstrap creates new accounts with prompted passwords and explicit admin
intent, recording actor kind `local_bootstrap`; it never promotes or overwrites
an existing account. It is a direct-DB local administration tool, not an external
identity system. Public registration rejects privilege fields. No credentials
are seeded or recorded in audit. Identity changes require review before merge or
external activation.

T02 validates only HTTPS github.com references and conservative relative bundle
paths. References remain visibly unverified until T08. SQLite supports fast offline
API/UI checks; only isolated PostgreSQL tests establish migration, constraints and
concurrent-update behavior. This distinction is retained in verification reports.

## ADR-013 — T03 explicit simulation and versioned environment policy

**Accepted implementation direction (T03), 2026-09-11.** Support only local runtime
with an explicitly configured `DEPLOYMENT_EXECUTOR=simulated`. Organization mode
is rejected until external identity exists; real sandbox mode is rejected until
GitHub execution is implemented. A local simulated environment named "sandbox"
does not enable the real sandbox runtime. Existing `.env` files need explicit
simulation opt-in. Validation diagnostics suppress input values.

Environment records approve a set of bundle targets and carry simulated workspace
references, enabled state, self-approval policy (default false), and a version.
Only platform admins manage them or their application bindings. Readers see only
environments bound to visible applications. No external resource or permission is
created, checked or granted.

Binding config schema 1 contains only bounded integer synthetic row count/runtime
settings. This intentionally excludes arbitrary string variables, commands, URLs,
credential values and unapproved compute references; later template/integration
tasks must explicitly extend the contract when needed. Config PATCH replaces the
whole typed object with defaults for omitted fields.

Environment-row locks serialize policy edits and binding writes on PostgreSQL.
Every environment change, including rename, conservatively increments associated
binding versions and audits each affected application in one transaction. Removed
targets/disabled environments preserve history but block binding commands. Future
revision/approval logic must capture and recheck environment and binding versions.

The explicit local seed accepts an existing active admin ID, creates only the
simulated environment, and refuses to overwrite changed policy. The identical
repeat does nothing. It is a direct-DB local administration helper, not a provider
adapter. No actual simulation execution is introduced before its owning task.

## ADR-014 — T04 durable queue with a fixed simulated probe

**Accepted implementation direction (T04), 2026-09-11.** Use PostgreSQL queue rows,
short synchronous transactions, `FOR UPDATE SKIP LOCKED`, renewable leases and
monotonic fencing. No broker or FastAPI background execution. Fencing covers
related probe results, attempts, reservation release and audit in one transaction.
Use database wall time after locks and recheck after flush; stale workers discard
results. Preserve requester identity while recording worker identity separately.

Keep an explicit typed, side-effect-free probe to exercise infrastructure without
an arbitrary task API. Its success path is available only via local CLI/service.
Closed deterministic failure scenarios support tests. Expiry first reconciles;
only established safe outcomes may retry. Unknown work retains the binding
reservation. An operator reason schedules observation and cannot force success;
retain only its digest to avoid pasted credentials in audit/history.

Store idempotency in command records so recovery endpoints have the same replay
contract as initial submission. Retries create linked operations after current
policy checks. Admin/owner status does not imply operator rights. API and worker
both enforce current grants, lifecycle and environment/binding eligibility.

Public readiness reports database/worker availability without diagnostics;
global queue telemetry is admin-only. No provider readiness, exactly-once external
execution, workspace capacity management or organization identity is implied.

## ADR-015 — Replace Streamlit before T05

**Accepted user direction, 2026-09-11; implemented in T04a, pending review/merge.** After T04
merges, replace Streamlit with React + TypeScript built using Vite before starting
T05. The backend now provides enough real workflows to support a useful UI;
migrating while the UI is small avoids implementing future feature screens twice.
This supersedes ADR-001's initial UI choice, not its FastAPI/worker/PostgreSQL design.

Reuse existing API contracts, accounts, data, roles, services and worker behavior.
Build the replacement alongside Streamlit for verification, starting with login
and application list/register/detail, then current administration and operation
workflows. Retire Streamlit only after equivalent browser workflows pass and
Docker/startup documentation is updated. Subsequent tasks build their UI in React.

The migration includes coherent navigation/forms/status feedback, accessibility,
API failure/session-expiry handling and reviewed browser authentication storage.
Server-side Streamlit session state is not a browser session design. Keep server
credentials/signing keys out of frontend assets and retain API-side authorization,
optimistic version checks and idempotency. Small API additions must retain scoped
visibility and receive their own contract/behavior checks.

Introduce a locked, project-local frontend toolchain and browser tests while
preserving Python/uv backend verification. Supporting component/routing/data
libraries and their versions are implementation choices; no packages are installed
by this decision. T04a has now cut over after browser parity passed; see ADR-016.
No T05 features, speculative dashboards, provider activation or organization
identity redesign are part of the migration. T05 depends on T04a completion.

## Questions reserved for their implementation gates

| Question | Needed by | Default until resolved |
|---|---|---|
| Which GitHub repository/account and visibility? | T08 real verification | Mocked adapter + local generated download |
| How will GitHub authentication be supplied? | T08 real verification | Credential reference only; no token in task payload |
| Which workspace, compute, output location, and spending exposure? | T10 activation | Simulation; real gate pending |
| Which approval enforcement/identity model and hosting does a company need? | T13 | No organization-readiness claim |
| Should users create new repositories or request external/data access? | Later scope | Existing repos and platform access only |

These questions are deliberately not prerequisites for T01–T07/T11. Agents should
progress through local work rather than repeatedly asking for unavailable accounts.

## ADR-016 — Local browser sessions and a static React runtime

**T04a implementation, 2026-09-11; pending human review/merge.** Use React,
TypeScript and Vite with Node 24.21.0 / npm 11.19.0, exact direct dependency
versions and `frontend/package-lock.json`. Python remains managed by uv.
The selected visual direction is a clean light interface with a compact sidebar.

Serve built assets through nginx and proxy `/auth`, `/api`, `/health` and `/ready`
to FastAPI on the same browser origin. Keep host port 8501 for Docker users;
Vite development uses 5173 with an equivalent server-side proxy. Neither frontend
runtime nor build receives root `.env`. Vite disables env-file discovery. The
frontend has no database or provider access; FastAPI and the worker retain policy,
transactions, version checks, audit and durable work.

Browser login uses a separate `/auth/session` endpoint returning the current user
and an HTTP-only, SameSite=Strict, host-only cookie containing the existing expiring
JWT. No bearer token is exposed to JavaScript, localStorage or sessionStorage.
The cookie is Secure for direct HTTPS requests; supported Compose development
is loopback HTTP. A TLS termination/proxy-trust design is a separate activation
review, not an organization deployment claim. Existing `/auth/login` bearer
clients and existing account hashes remain compatible; no migration is needed.
Cookie-authenticated writes and browser login/logout require `X-Control-Plane:
browser` plus an Origin matching the request origin or explicit CORS allowlist.
Proxies preserve the original Host. Login/logout responses are not cacheable.
Logout clears the browser cookie; it does not revoke a copied JWT before expiry,
matching the existing development bearer-token limitation. Active account and
current grants are checked on every request. Organization SSO and global session
revocation remain out of scope.

`GET /api/v1/applications/{id}/capabilities` returns current UI affordances derived
from existing policy; services still authorize every mutation. Forms capture the
version displayed when opened. Operation commands retain an idempotency key per
operation/action/payload in workspace memory across retries and dialog reopen;
logout/full reload clears that memory. After a full reload, inspect operation
history before repeating uncertain work. The API remains the durable deduplication
boundary. No new command-submission endpoint is introduced.

Playwright exercises the real FastAPI and worker services using disposable SQLite
fixtures; PostgreSQL migration/concurrency tests remain separate and mandatory in
CI. A Docker test image packages Chromium's OS libraries for hosts without them.
This avoids requiring a host-global browser dependency installation. Browser tests
cover UI behavior rather than reimplementing backend policy in mocks.

## ADR-017 — Deterministic generation, local artifacts and offline-only validation

**T05 implementation, 2026-09-12; pending human review/merge.**

*Execution mode names what actually happens.* Generation and validation carry
`execution_mode="local"`, not `"simulated"`. They are real work this machine
performs and produce real artifacts; labelling them simulated would be inaccurate
in the opposite direction from the risk ADR-013 guards against. Deployment
execution remains `simulated` and is not implemented. The queue's check constraint
enforces the pairing in both directions: `queue_probe` must be `simulated`,
`bundle_generation`/`offline_validation` must be `local`.

*Archives are byte-reproducible.* Entries are rendered from reviewed on-disk
assets, sorted by target path, given a fixed 1980-01-01 timestamp, fixed `0644`
permissions and a fixed Unix create-system, and stored **uncompressed**. Deflate
output can differ between zlib versions, so compression would make the digest
depend on the generating machine. The template's own identity is a content digest
over its manifest plus every asset; a registered version whose assets change is
refused rather than silently regenerating different content under the same name.

*The client supplies two parameters.* Application slug comes from the registry and
bundle target from the environment binding, so a caller cannot direct generation at
an unapproved target or impersonate another application. Only `package_name` and
`synthetic_output_path` are client input, both strictly patterned. Row count and
timeout come from the T03 binding configuration. The payload has no credential,
command, URL or template-path field, and unknown fields are rejected.

*Artifacts are content-addressed in a configured shared mount.* The store writes
atomically under `sha256/<aa>/<bb>/<digest>`, deduplicates identical content, and
re-hashes on every read so content that no longer matches its recorded digest is
refused rather than served. Compose mounts the same directory into the API and the
worker; without that, downloads would fail after either process restarted. Moving
hosts requires migrating this directory, as architecture.md already states.

*Local delivery work takes no binding reservation.* Reservations exist to serialize
work competing for one binding's external state. Generation and validation touch
none, so reserving would let an unresolved probe block generation, and a queued
generation block a deployment, for no safety gain. Idempotency keys still
deduplicate submissions. Consequently `POST /operations/{id}/retry` returns 409
`unsupported_retry` for these kinds: retry re-runs work under the **operator**
authority the queue requires, while generation and validation are **developer**
actions. Submitting a new generation is the supported path and is equivalent,
because generation is deterministic. The worker rechecks the role each kind needs.

*Offline validation is never workspace validation.* `ValidationResult.scope` is
constrained to `offline` in the database, and the stored JSON report states in
every copy that no workspace, cluster, credential or network was contacted, that
no generated code was executed, and that dependencies were parsed rather than
installed. Checks parse: `ast.parse` for Python, `tomllib` for `pyproject.toml`
and `uv.lock`, and comment-stripped structural reads of the bundle and workflow
files. The *operation* succeeds when the check runs; whether the artifact passed
is the separate validation result, surfaced as a `validation_failed` diagnostic.

*The generated project is dependency-free on purpose.* Its runtime and tests use
only the standard library, so `uv sync --locked` and its test suite run with no
network at all, and `scripts/check_generated_project.py` can prove the acceptance
criterion offline in CI. Its Databricks compute variables have **no defaults**:
a real deployment must supply values verified for an actual workspace and budget.
Its deployment workflow is dispatch-only and fails before any bundle command until
a repository administrator explicitly enables it. Adding a third-party dependency
to the template requires re-locking and loses the fully offline property.
