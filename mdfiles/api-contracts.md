# API contracts

Status: T02 `/api/v1` registry endpoints are implemented; later task rows remain planned. Existing `/auth/*` remains the development login
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

## T02 implemented details

The T02 rows above are implemented. Supporting paginated reads are
`GET /teams/{id}/members` (admin or current member),
`GET /applications/{id}/roles` (application read permission), and
`GET /audit-events` (platform admin only, including membership/bootstrap events).
All lists use permission filtering before `(created_at,id)` keyset pagination;
cursors are base64 JSON, validated and scoped to the endpoint/actor. They are
navigation tokens, not authorization or a frozen snapshot of changing records.
Responses include `X-Request-ID`, generated by the server; mutation audits retain
that ID. Validation errors include locations/types, never echoed input values.

Public `/auth/register` rejects unknown fields, including active/admin flags.
`/auth/me` returns `is_active` and `is_platform_admin`; existing email/username
form login and email-subject bearer tokens are retained. Inactive users cannot
log in or use existing tokens. Global admin creation is only the explicit local
`python -m bootstrap ... --admin` command; no public admin-grant endpoint exists.

Creation grants the creator direct developer and viewer assignments. Even admins
must be members of the owning team to register. Owner and data owner must be
existing active users; they need not be members of that team. The owning team
receives no implicit application role. Owner/data owner get read access; only
owner/admin can manage assignments and accountability fields. Editing name,
description or source requires an explicit developer role, including for admins.

`PATCH /applications/{id}` accepts `expected_version` and one or more non-null
mutable fields. Slug, lifecycle, creator and verification state cannot be patched.
Ownership fields are `owning_team_id`, `owner_user_id`, `data_owner_user_id`.
Other fields are `name`, `description`, `repository_url`, `bundle_root`. A mixed
patch requires both management and developer permissions. The database update
compares and increments version atomically; stale writes return `stale_version`
409. Source changes clear verification. No archive endpoint is added before T11.

Repositories accept only `https://github.com/<owner>/<repository>` (optional
`.git` is normalized away), without credentials, port, query, fragment or trailing
slash. Bundle root is `.` or slash-separated ASCII alphanumeric/underscore/dot/
hyphen segments, excluding empty, `.` and `..` segments. There is no network
verification in T02; `repository_verified_at` remains null.

Successful mutations and their audit event commit together. Conflicts return a
sanitized `registry_conflict` 409; invalid references return 422; unexpected
failures return `internal_error` 500 and roll back. Audit reads have no edit/delete
endpoint. Failed requests do not produce success audit rows. User/team deletion
is not exposed; database foreign keys retain references without delete cascades.

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
