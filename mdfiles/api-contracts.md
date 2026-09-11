# API contracts

Status: planned `/api/v1` API. Existing `/auth/*` remains the development login
surface initially. Implement endpoints with their tasks; this document does not
claim they exist. Keep services usable by API and worker without importing routers.

## Common behavior

- UUID strings for platform IDs, RFC 3339 UTC timestamps, typed enums, bounded
  strings, validated repository/bundle paths, explicit Pydantic response models.
- Bearer authentication; unauthenticated `401`, known resource without action
  permission `403`, inaccessible resource lookup `404`, conflict `409`, invalid
  payload `422`. Do not leak private records through counts or errors.
- Error envelope: `{"error":{"code":"approval_required","message":"...",
  "request_id":"...","details":{}}}`. Sanitize provider diagnostics. T02
  standardizes this for platform endpoints, including validation errors.
- List endpoints: `?limit=20&cursor=...`, limit range 1–100; stable ordering by
  `(created_at,id)`, opaque validated cursor. Response:
  `{"items":[],"next_cursor":null}`. Apply permission filters before pagination.
- Async command: `202`, `Location: /api/v1/operations/<id>` and
  `{"operation_id":"...","status":"queued","execution_mode":"simulated"}`.
  Require `Idempotency-Key`; same accepted command returns original operation and
  current status with `202`, even if already terminal.
- Synchronous create: `201` with resource/Location; update/action: `200`; role
  removal: `204`. Mutable registry updates include `expected_version`; stale `409`.
- Every mutation records actor, target, and outcome. Worker execution adds its
  executor identity without replacing the original requester.

## Planned endpoints

All paths below are under `/api/v1`. Permissions are defined in
[domain-contracts.md](domain-contracts.md).

| Task | Method and path | Contract |
|---|---|---|
| T02 | `POST /teams`, `GET /teams` | Admin create/list; users can list their teams |
| T02 | `POST /teams/{id}/members`, `DELETE /teams/{id}/members/{user_id}` | Admin membership management; audited |
| T02 | `POST /applications`, `GET /applications`, `GET /applications/{id}` | Create, permission-filtered list/detail |
| T02 | `PATCH /applications/{id}` | Metadata/ownership update with policy and version checks |
| T02 | `POST /applications/{id}/roles`, `DELETE /applications/{id}/roles/{assignment_id}` | Owner/admin explicit assignments and revocation |
| T02 | `GET /applications/{id}/audit-events` | Paginated visible history |
| T03 | `POST /environments`, `GET /environments`, `PATCH /environments/{id}` | Admin writes; authorized reads; no secrets |
| T03 | `POST /applications/{id}/bindings`, `PATCH /applications/{id}/bindings/{binding_id}` | Register/configure approved target; versioned |
| T04 | `GET /operations/{id}`, `GET /applications/{id}/operations` | Status, progress, sanitized errors, observations |
| T04 | `GET /operations/{id}/attempts` | Paginated attempt history |
| T04 | `POST /operations/{id}/cancel` | `202` cancellation intent; terminal no-op returns current result |
| T04 | `POST /operations/{id}/retry` | `202` new operation; resolved safe failures only |
| T04 | `POST /operations/{id}/reconcile` | `202` schedule operator-requested reconciliation; evidence required for manual resolution |
| T05 | `GET /templates` | Approved template versions/input contracts |
| T05 | `POST /applications/{id}/generations` | `202`; template version + validated parameters -> artifact |
| T05 | `GET /artifacts/{digest}` | Authorized download by associated application; opaque storage details |
| T05 | `POST /applications/{id}/revisions` | `201`; reference already captured artifact, binding, nonsecret config |
| T05 | `POST /revisions/{id}/validations` | `202`; explicit validation scope |
| T05 | `GET /applications/{id}/revisions`, `GET /revisions/{id}` | Snapshot and validation/approval references |
| T06 | `POST /revisions/{id}/approvals` | `201`; decision, scope digest, validation result ID, reason |
| T06 | `POST /applications/{id}/deployments` | `202`; approved revision + binding, developer/operator |
| T06 | `GET /applications/{id}/deployments`, `GET /deployments/{id}` | State, execution mode, source, target, external IDs/links |
| T07 | `POST /deployments/{id}/runs` | `202`; allowlisted job key + bounded typed parameters |
| T07 | `GET /deployments/{id}/runs`, `GET /runs/{id}` | Genuine or explicitly simulated result and observation time |
| T08 | `POST /applications/{id}/source-captures` | `202`; resolve repository ref to immutable commit/artifact |
| T08 | `GET /applications/{id}/ci-runs` | Paginated observed checks associated with exact source commit |
| T11 | `POST /applications/{id}/access-requests`, `GET /applications/{id}/access-requests` | Request own access; owner/admin sees all, requester sees own |
| T11 | `POST /access-requests/{id}/decision` | Owner/admin approve/reject; cannot self-escalate through requester role |
| T11 | `POST /applications/{id}/archive` | Version check, no unresolved operations; retain history/data |

T08 extends revision input to reference a completed source capture. Repository ref
resolution is asynchronous; clients cannot assert an arbitrary commit was verified.
GitHub status refresh is worker-driven, not fan-out during page requests.

## Example: registration and deployment

```json
{
  "slug": "synthetic-sales",
  "name": "Synthetic sales processing",
  "description": "Sandbox batch application",
  "owning_team_id": "<team UUID>",
  "owner_user_id": 1,
  "data_owner_user_id": 1,
  "repository_url": "https://github.com/example/synthetic-sales",
  "bundle_root": "."
}
```

Registration records a reference; `repository_verified_at=null` until T08
verification. Restrict supported repository hosts and URL forms; reject embedded
credentials, arbitrary filesystem paths, traversal, and unapproved hosts.

```http
POST /api/v1/applications/<application-id>/deployments
Authorization: Bearer <development session>
Idempotency-Key: <client-generated UUID>
Content-Type: application/json

{"revision_id":"<revision UUID>","binding_id":"<binding UUID>"}
```

Server resolves the immutable source, approval, target, and executor. Clients
cannot inject a command, workspace URL, executor identity, or approval actor.

## UI requirements

Streamlit uses authenticated HTTP calls with timeouts; no direct DB access or
deployment credentials. Each task includes its corresponding screen rather than
leaving all UI work to the end. Show source revision, approval scope, target,
execution mode, external run links, freshness, and pending cancellation accurately.
Hiding buttons helps usability but never replaces server authorization.
