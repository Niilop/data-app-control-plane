# Domain and workflow contracts

Status: T02–T07 registry, queue, preparation, approval and simulated deployment entities are implemented; later task entities remain proposed. Introduce entities in their owning task,
not all at once. New entities use UUIDs, timezone-aware UTC timestamps, explicit
foreign keys, and database constraints for uniqueness. Historical AI tables remain migration-only metadata after T01a; no runtime AI
features are retained. Existing user IDs may remain
integers; external identity later maps issuer + subject to that internal user.

## Entity catalogue

| Entity | Essential fields / invariants | Task |
|---|---|---|
| User extensions | active flag, platform-admin assignment; never self-selected at registration | T02 |
| Team / TeamMembership | stable ID, name; unique team/user membership | T02 |
| Application | ID, unique slug, name, description, owning team, owner user, data-owner user, repository URL, bundle root, lifecycle, created_by, version | T02 |
| ApplicationRole | application, user or team subject, role; unique assignment; exactly one subject kind | T02 |
| Environment | name, workspace reference, enabled flag, allowed executor, self-approval policy | T03 |
| EnvironmentBinding | application + environment unique, bundle target, allowed nonsecret config, version | T03 |
| TemplateVersion | template name/version unique, content digest, parameter schema, active flag | T05 |
| Artifact | SHA-256 digest, storage key, size, media type, provenance; content immutable | T05 |
| DeploymentRevision | application, source kind, repository/commit or artifact digest, template version, binding ID, binding snapshot, config snapshot/digest, requester | T05 |
| ValidationResult | revision, validator/tool version, offline/workspace scope, result, report artifact, timestamp; never conflates offline with workspace validation | T05 |
| Approval | revision, scope digest, approver, decision/reason, policy version, timestamp; append-only | T06 |
| Deployment | application, binding, revision, requester, executor, execution mode, operation ID, status, external references, last_observed_at | T06 |
| Operation | type, payload version, payload, requester, idempotency key/hash, state, not_before, lease fields, correlation ID, result/error, cancellation flag, parent operation | T04 |
| OperationAttempt | operation, attempt number unique, worker/token, start/end, external references, outcome | T04 |
| JobRun | deployment, resource key, requester, operation, execution mode, provider run ID, status/result, last_observed_at | T07 |
| AccessRequest | application, subject, requested platform role, requester, reason, decision and decider | T11 |
| AuditEvent | actor, action, target type/ID, outcome, request/operation IDs, sanitized detail, timestamp | T02 |

Configuration snapshots and artifacts are immutable. Mutable application metadata
uses optimistic version checks. Prevent deletion of referenced users, revisions,
approvals, deployments, and audit through cascades; deactivate/archive instead.
Secrets are credential references resolved by the authorized process, never values
in these fields. External URLs must be constructed/validated against approved hosts.

For an adopted repository without known generation provenance, select and record
the supported template contract version it passed; do not claim it was generated
from that template. Changing source/config/target always creates a new revision.

## Permission model

Roles are application-scoped, assigned directly or through a team. Platform admin
is a separate global role. Effective roles are the union of current assignments;
no implicit role inheritance unless listed here.

| Action | Required role / relationship |
|---|---|
| Register application | Active development user; must belong to owning team; creator receives developer + viewer |
| Read application/history | Any application role, recorded owner/data owner, or platform admin |
| Edit metadata, request generation/revision/validation/deployment | Developer |
| Approve deployment revision | Approver; independent actor unless binding explicitly allows local self-approval |
| Execute approved deployment, run job, recover/cancel work | Operator |
| Request platform role | Active user for a known application ID; response must not disclose private application details |
| Approve platform access | Application owner or platform admin; cannot grant platform admin through this endpoint |
| Manage ownership/role assignments, archive | Application owner or platform admin |
| Manage teams, environments, binding configuration | Platform admin |
| Grant global platform admin | Explicit administrative bootstrap/management path; audited, never public registration |

A developer's deployment request stays pending until an operator submits it, or
the requester also has operator. To keep the initial API small, T06 requires both
developer and operator for `POST /deployments`; separate handoff is deferred.
Local demo users can hold all roles. Operator-only users can execute via a future
handoff endpoint, and can already run/cancel/recover permitted existing operations.

Neither data ownership nor a platform role confers Git, Databricks, or data
permissions. Revoking a role immediately affects API decisions and queued work.
Before deployment submission, recheck requester roles and that the approving actor
remains authorized. Role changes after external submission cannot promise to undo
the action; record them and request cancellation when policy requires it.

T02 clarification: owning-team membership is required even for administrator
registration and grants no implicit read access afterward. The creator receives
direct developer/viewer roles; recorded owner/data owner receive read access by
relationship. Accountable users must exist and be active but need not belong to
the owning team. Platform admin has explicit read/management rights only;
metadata/source editing still requires a developer assignment. Bootstrap creates
new local users with explicit admin intent and an audit event; no public route
can grant global admin. Account deactivation has no management UI/API in T02,
but authentication and every platform policy enforce the current active flag.

## T03 environment and binding invariants

Environment and EnvironmentBinding are implemented as UUID/UTC records with
positive versions. Environment name is unique; each application/environment pair
has one binding, enforced by a unique database constraint. Foreign keys preserve
references; neither deletion nor external retirement is exposed.

Only active platform admins create/edit environments and bindings. Application
readers can read their bindings and environments referenced by their visible
applications; unbound/private environments remain hidden to nonadmins. Owner,
data owner and developer roles do not grant binding or infrastructure authority.

An enabled environment approves an explicit nonempty set of bundle targets.
Bindings reject unknown/disabled environments, unapproved targets and archived
applications. A disabled environment or removed target preserves existing binding
history but marks it unusable. Re-enabling/restoring the target can make it usable
again; this is recorded policy, not proof of deployment or external availability.

T03 accepts only simulated workspace references and executor. Self-approval is off
by default; an explicit local simulated environment policy can enable it for future
approval tasks. Typed config schema version 1 has only bounded integer
`synthetic_row_count` and `max_runtime_seconds`, with unknown keys and inline
credentials rejected. It has no compute, credential, URL, command or arbitrary
variable fields. Later template/resource contracts can extend the schema explicitly.

Both environment and binding updates require `expected_version`. Environment
changes serialize with binding creation/update under an environment row lock,
bump all associated binding versions, and write attributable application/admin
audit in the same transaction. Future approval scope must capture/recheck these
versions as well as source/config. No approval or worker is implemented in T03.

## State contracts

**Application:** `registered -> active -> archived`; registered may also archive.
Registration permits preparation; first successful deployment activates. A failed
deployment does not archive or delete an application. Archive preserves data,
rejects new commands, and requires no unresolved conflicting operation.

**Revision:** source/config is immutable; validation and approval are separate
append-only records. UI derives `prepared`, `validation_failed`,
`awaiting_approval`, `approved`, or `rejected`. A new validation report does not
rewrite an old approval. Bind approval to the accepted validation report and exact
scope digest (source, artifact, template contract, config, binding snapshot,
target, execution mode, policy version). An environment policy/binding change
invalidates execution eligibility and requires preparation/approval again.

**Operation:**

```text
queued -> running -> succeeded | failed | cancelled
              |-> retry_wait -> running
              |-> reconciling -> running | succeeded | failed | needs_attention
queued/retry_wait -> cancelled
needs_attention -> reconciling  (operator action with evidence)
```

Lease expiry causes reconciliation. A running operation can have cancellation
requested without changing its state to cancelled. Terminal outcomes do not
transition to running; manual retry creates a new linked operation.

**Deployment:** `queued -> deploying -> succeeded | failed | unknown | cancelled`.
Unknown external outcome stays unknown until observed. A failed deployment may
leave external resources; preserve observations. Keep the last successful
deployment separately from the latest attempt. Deployment success does not imply
data-job success.

**JobRun:** `queued -> running -> succeeded | failed | cancelled | unknown`.
Retain raw provider lifecycle/result values alongside normalized state; only
observed completion and required output verification establish success.

**AccessRequest:** `pending -> approved | rejected | cancelled`. Approval and
platform-role insertion share one transaction and audit event. Repeating approval
does not create duplicate assignments. Revocation removes an effective assignment
with audit; if a second team/direct grant still confers the role, show that fact.

## Idempotency and concurrency

Require an `Idempotency-Key` on asynchronous command submission. Uniqueness scope
is actor + route/action + target + key. Store a canonical request hash: repeat of
the same request returns the original operation, different payload returns `409`.
Keep keys with operation history for the initial version.

One unresolved deployment per application/environment binding; use a database
constraint/atomic reservation, not a read-then-insert check. A second conflicting
request returns `409` with the existing operation ID if the actor can read it.
Do not release on worker loss or unknown provider outcome. Idempotency keys do
not by themselves deduplicate GitHub or Databricks actions.

## T04 concrete queue contract

Operation payload schema 1 currently supports only the internal simulated probe.
`OperationCommand` holds the idempotency scope/hash and references the resulting
operation. `OperationReservation` has a primary key on binding ID and unique
operation ID. `QueueProbe` is the related request/result record used to exercise
transactional enqueue and fenced completion. `WorkerHeartbeat` records polling/
lease-renewal freshness. These are separate from historical BackgroundJob/Pipeline.

Each claim increments a fencing token and creates a unique operation/token
attempt with a persisted correlation UUID and execute/reconcile phase. Execution
attempts, not reconciliation observations, consume the maximum three-execution
budget. Leases last 30 seconds and renew every 10 seconds; timestamps for lease
checks use PostgreSQL `clock_timestamp()` after row locking. Result writes and
reservation release are part of the fenced transaction, including a final expiry
check after flush. Handlers do not hold a database transaction.

The probe has no external side effects. After lease loss its reconciler can
establish that repeat execution is safe and schedules `retry_wait` before the
next execution. Deterministic unknown scenarios intentionally cannot establish an
outcome: observation changes them to `needs_attention`, retaining reservations.
Operator evidence is a reason for another observation, not a way to override
results. Future handlers must implement their own provider reconciliation; never
infer safe resubmission from lease expiry or loss of requester authorization.

Worker observations retain the original requester as audit actor, plus operation
ID, worker UUID and fencing token in safe details. Recovery actions record the
acting operator. The initial probe does not implement external workspace limits,
provider cancellation or exactly-once external execution.

## T05 implemented preparation contract

One approved `TemplateVersion` uses the immutable ID `python-batch:1.0.0`, content
SHA-256 and closed parameter schema. Its active flag may be disabled; content
changes require a new version. Only `package_name` is accepted (prefix `batch_`,
then a lowercase letter and bounded lowercase letters/digits/underscores).
Application slug and target/config come from the existing registry and binding.

`Generation` records application, operation, template, parameters and the complete
binding/environment snapshot. A successful fenced completion associates an
`Artifact` by SHA-256, size and media type. Provenance/access is through generation
or report associations, not possession of the digest. Identical bytes may be shared
across applications without granting one application access to another's history.

Generation and validation require an explicit developer role, including for admins.
They reserve their binding using the existing queue reservation. Snapshot versions,
active account/roles, lifecycle, environment policy and approved template are
rechecked before execution and successful completion. Operation mode is `offline`;
the captured target's mode remains `simulated`. Recovery requires operator; retry
also checks developer and the original binding version, preserving source inputs.

Revision creation requires a completed generation owned by the application and an
unchanged complete binding snapshot. It records generated source, artifact/template
digests, config digest/snapshot, policy snapshot and requester; no update/delete API
exists. PostgreSQL rejects updates/deletes to revisions, artifacts and validation
reports. Validation reports are append-only and bind an exact revision with
`scope=offline`, validator `static-v1`, passed/failed result, report digest and time.
A successfully completed validation operation may produce a failed check report;
operation success is completion of the check, not workspace or deployment success.

## T06 implemented approval and simulated deployment

`Approval` is append-only in the ORM and PostgreSQL. Its canonical SHA-256 scope
contains the application/revision IDs, generated source kind, artifact digest,
template ID/content digest, configuration/digest, complete binding/environment
snapshot (including target, workspace, versions and self-approval policy), simulated
mode/executor, policy version `local-simulation-v1`, and the exact passed offline
report ID/digest/validator/result. Failed or unrelated reports cannot be approved.
A newer decision for the **same scope digest** supersedes earlier decisions for
execution. A new validation report is a different scope and does not silently
rewrite an approval. Rejection cannot itself authorize a deployment.

Approval requires an active approver role; admin/owner alone is insufficient.
An approver matching the revision requester or deployment submitter is permitted
only by an explicitly enabled local environment policy and an acknowledged approval.
The policy and acknowledgement are stored, and the approval/submission audit records
self-approval context. Independence is checked again for retries by another actor.

Submission requires both developer and operator, explicit `execution_mode=simulated`,
revision/binding/approval IDs and an idempotency key. The worker rechecks active
requester and approver, current roles, application lifecycle, complete binding policy,
active template and exact latest approval before execution and before successful
completion. Eligibility is refreshed after waiting on the environment lock.

Deployment records are distinct from operations. One operation owns one deployment;
manual retry creates both anew and links `retry_of`. Queued cancellation updates the
deployment atomically. Claim/reconciliation maps to deploying/unknown; terminal
state, resource observations, reservation release and audit share the lease fence.
The closed `success`/`partial_failure` scenarios are explicitly simulation-only.
Partial failure records a simulated created resource, never a real external ID.
Reconciliation can safely repeat this handler because it has no external effects;
revoked authorization during reconciliation retains the existing conservative
needs-attention/reservation behavior. No operator override can force success.

Last success is queried independently per binding from successful deployment history,
ordered by observation time and ID. Later failures never erase it. First success
activates a registered application with an atomic version increment; deployment
success does not claim that a data job ran. T07 adds separate run records as described below.

## T07 implemented simulated job runs

`JobRun` is separate from deployment and operation state. It references one
successful simulated deployment, its application, requester and unique operation.
Only the ready `synthetic_job` resource in the approved template is runnable.
The command accepts strict integer `parameters.row_count` in 1–10,000 (default 100)
and explicitly simulated `success`/`failure` fixtures. These are run inputs rather
than edits to the immutable deployment configuration. Provider run ID stays null;
no fabricated provider ID or local path appears in results.

An active operator is sufficient; developer, owner or admin status alone is not.
The API, worker authorization and successful completion check the current operator,
active application, unchanged complete revision/binding policy, approved template,
successful deployment and ready job. Eligibility is refreshed after blocking policy
locks. Approval evidence remains the historical evidence of the successful deployment;
running an already deployed job is not a new deployment approval or self-approval.
It does not require the original deployer or approver to retain their roles.

Submission commits run, operation, binding reservation, command key and audit together.
Runs share the existing conservative one-unresolved-operation-per-binding rule with
preparation/deployment work. Matching keys replay the original operation after current
operator checks; changed inputs conflict. Run records and results commit with the
operation/attempt/audit lease fence. A fixed simulator computes a synthetic summary;
completion verifies its row count and arithmetic total before recording success.
Results retain simulated lifecycle/outcome and output verification, never claiming
actual Databricks execution. Job failure cannot change deployment history/last success.

Queued cancellation updates the run and releases its reservation. Manual retry
creates a linked operation and a new run after current checks. Lease loss first
marks unknown and reconciles; safe replay is possible because the handler has no
external effects. Revoked authorization during reconciliation conservatively retains
unknown state and reservation. Operator reconciliation cannot force a result.
