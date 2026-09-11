# Architecture decisions and open gates

Recorded 2026-09-11. “Accepted direction” reflects user choices; “provisional” is
an implementation default that can change with evidence. When changing a decision,
retain its history, rationale, affected contracts/tasks, and replacement decision.

## ADR-001 — Local-first modular monolith

**Accepted direction.** FastAPI + independently runnable worker + PostgreSQL,
Streamlit for initial UI, shared business services. Local hosting supports a
single developer with essentially no cloud budget. Organizational hosting later
does not require replacing core workflows. No microservices, Azure hosting,
message broker, or Redis dependency initially.

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
