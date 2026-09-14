# Agent handoff

Inspect Git status, preserve unrelated changes, verify prerequisites on updated
main, and read AGENTS.md before creating the next task branch. This handoff records
implementation; it does not imply that its PR has merged.

## Implemented state

Updated main on 2026-09-14 contains T01–T04a; T04a merged as `6503ec1` via PR #10.
T05 is proposed separately in [PR #11](https://github.com/Niilop/data-app-control-plane/pull/11)
and is not in this documentation branch's main baseline. Inspect its current
status before continuing; do not recreate its implementation. AI/chat/RAG/LLM/inference remain removed;
historical tables and all migrations through `007_durable_operations` are retained.

The Terraform planning update adds T09a between T09 and T10, plus ADR-018 and the
affected scope/architecture/integration/testing/map contracts. It adds no Terraform
configuration or runtime behavior. DAB remains the application delivery tool;
infrastructure is a separate administrator responsibility. No external activation
is authorized by this documentation change.

The platform provides development accounts/admin bootstrap, teams/memberships,
owned applications, direct/team roles, versioned metadata, simulated environment
bindings, filtered paginated reads and transactional audit. Its separate PostgreSQL
worker uses durable operations, reservations, idempotent commands, leases/fencing,
current authorization, heartbeats, safe bounded retry, cancellation and reconciliation.
Only the fixed simulated queue probe runs; no arbitrary task HTTP endpoint exists.

T04a replaces Streamlit with React + TypeScript + Vite:

- Clean light sidebar layout, accounts/profile, application list/register/detail/
  edit, ownership and role controls, teams/memberships, environment policy/bindings,
  audit history and operation/attempt recovery. Paginated reads, error/loading/empty
  states, simulation labels, responsive navigation and keyboard dialog/tab controls.
- Versioned edit controls stay disabled while fresh records are loading, and
  lists visibly report refresh progress. Forms retain the version captured when
  opened. Recovery keys persist per
  operation/action/payload in workspace memory across transport retries/dialog
  reopen. API policy/version/idempotency and worker policy remain authoritative.
- Browser `POST/DELETE /auth/session` uses an HTTP-only, SameSite=Strict cookie
  holding the existing expiring JWT. Login/logout and cookie-authenticated writes
  require a custom header and trusted Origin. Existing bearer login remains.
  No browser localStorage/sessionStorage tokens; no account/password reset.
- `GET /api/v1/applications/{id}/capabilities` exposes four current affordances;
  services still authorize mutations. Direct/team revocation remains immediate.
- Node 24.21.0 / npm 11.19.0, exact direct dependencies and package-lock.json.
  Python stays on uv. Streamlit runtime/dependencies/workspace/UI-only tests are
  retired after equivalent browser workflows passed.
- Docker frontend uses Node build then nginx static serving and same-origin API
  proxy on localhost:8501. Vite development uses 127.0.0.1:5173. Frontend does not
  receive root `.env`; Vite disables env-file discovery. `API_URL` is retired;
  `API_PROXY_TARGET` is a Vite server-only override. Existing `.env` is untouched.
- CI includes frontend lint/format/build/browser tests and production nginx smoke,
  alongside Python and isolated PostgreSQL jobs. See ADR-016 for session choices.

## Verification performed

For the 2026-09-14 documentation update, `git diff --check` passed. A stdlib check
run through uv passed for all nine changed Markdown files: 47 local links/anchors,
balanced code fences, the six handoff sections and T09a task ordering. Manual
review checked resource ownership and configuration-versus-activation boundaries.
Updated `origin/main` is `6503ec1`; GitHub confirmed PR #11 is open and draft.
Application tests and Terraform/provider commands were not run for this prose-only
change. No infrastructure configuration, installation or activation occurred.

Historical T04a verification on 2026-09-11/12:

- `uv sync --locked --all-packages --group dev` passed after lock cleanup.
- `uv run --locked pytest -q`: **125 passed** with network blocking enabled.
  TestClient ran outside the sandbox thread restriction. The total replaces nine
  Streamlit-specific cases with eight cookie/capability API cases; browser coverage
  is separate. Existing backend assertions and migration history are preserved.
- Ruff lint/format passed across the complete README/CI scope: **48 files**.
  `uv run --locked mypy`: **28 source files passed**.
- `npm ci`, frontend lint/format/type checks and Vite production build passed.
  **9 Chromium browser workflows passed** against a disposable real FastAPI/SQLite
  API with simulated worker fixtures. Coverage includes login/register/reload/logout,
  application edits/ownership/audit, teams, roles/revocation, environments/bindings,
  stale versions, validation, viewer denial, pagination, connection/session failure,
  cancel/retry/reconcile and lost-response idempotency. Desktop and 390px mobile
  screenshots were inspected; keyboard Escape restores focus.
- All Compose images built, quiet config validation passed, and existing local
  backend/worker/frontend services started while preserving the database volume.
  `/ready` via localhost:8501 returned ready. The four application services remain
  running. A read-only check confirmed the existing active administrator and
  migration head 007 remain present. No migration or reset was needed.
- An isolated production nginx/browser smoke passed routing, CSP, cookie login/
  reload, authenticated team creation, worker readiness and logout. Its fixtures
  use a separate temporary SQLite DB, with no root `.env` or application DB volume.
- Generated browser assets were checked against configured server secret values
  without printing them; no configured secrets or fixture credentials were found.
- Chromium could not run natively because WSL lacks its OS libraries; sudo requires
  interactive authentication. No host-global packages were installed. Tests instead
  used `tests/Dockerfile.browser`. Docker worked through regular Ubuntu via
  `wsl.exe`; this agent session's direct Docker CLI mount still returned I/O errors.
- Hosted [Platform CI run 34649546595](https://github.com/Niilop/data-app-control-plane/actions/runs/34649546595)
  passed at implementation commit `7cb2c2025a178ac4ebba5973c3a5f55e98b81aaa`.
  Actual logs confirm **125 offline tests** (12.70s), **15 PostgreSQL tests**
  (9.78s, no skips), **9 browser workflows** (30.6s), production nginx smoke,
  frontend checks and Python Ruff/mypy. The browser regression holds the real
  binding-list response and checks disabled edits, visible refresh progress and
  the updated version before saving. Handoff CI run 34649546592 also passed.
  PostgreSQL integration tests were not rerun locally. This final follow-up changes
  documentation only; application checks were not rerun locally for that edit.
  These are historical T04a checks, not verification of the Terraform plan.


## Remaining work and limitations

- Review existing T05 PR #11 and its current evidence before merge. This
  documentation branch does not include its implementation or reverify its checks.
- T09a is planned only. Provider/resource choice, backend bootstrap, credentials,
  live plans/applies and cleanup remain future work; the local demo and T12's
  scripted recovery work do not depend on infrastructure activation.
- Development logout clears the cookie but does not revoke copied JWTs before
  expiry. TLS termination/proxy trust, organization SSO and global revocation remain
  later work. Supported Compose development is loopback HTTP; direct HTTPS cookies
  are Secure. Current activity/grants are still checked for every authenticated call.
- Recovery keys survive dialog reopen and transport retry within the signed-in
  workspace, but full reload/logout clears them. Inspect operation history before
  repeating uncertain work after a full reload. The API is the durable boundary.
- User ownership/membership controls still use user IDs; teams/environments have
  paginated selectors. Application filtering applies to the displayed page only.
- Chromium is the browser tested. Firefox/WebKit and organization deployment are
  not verified. Browser SQLite tests do not establish PostgreSQL concurrency.
- Devstack integration remains unverified; `~/code/devstack` was absent. Existing
  local Compose uses the bundled pgvector/pg16 database. Preserve `.env`/volumes.
- No template generation, artifacts, revisions, approvals, provider adapters or
  deployments exist in the recorded main baseline. Unknown probes retain
  reservations until a supported outcome;
  no force-success API or exactly-once external execution claim exists.

## Next task

Inspect updated main and existing PR #11 for **T05 — Generate a bundle and capture
a revision**; continue/review that work if outstanding rather than recreating it.
If T05 has merged, use its current handoff for T06. Read the complete task and
contracts first and implement only the assigned bounded slice. Do not advance
beyond it, publish repositories, deploy real bundles, execute adopted arbitrary
repository code, or activate providers. Preserve current
policy/audit/version/idempotency rules.

Keep T09a scheduled after T09 and before T10; do not start Terraform with T05/T06.
When integrating the T05 handoff, retain this roadmap decision and its explicit
separation from application deployment. ADR-017 is used by T05's existing branch;
the Terraform decision uses ADR-018 to avoid an identifier collision.

## Files to read first

- `AGENTS.md`, `mdfiles/README.md`, T05 in `mdfiles/development-plan.md`, ADR-015/016
  and ADR-018 in `mdfiles/decisions.md`.
- `mdfiles/integrations.md`, artifact/revision/validation rules in
  `mdfiles/domain-contracts.md`, T05 API rows, `mdfiles/architecture.md` and
  `mdfiles/repository-map.md`.
- `backend/services/operation_service.py`, `queue_service.py`, `backend/worker.py`,
  operation/platform schemas and affected auth/policy services.
- `frontend/src/App.tsx`, `api.ts`, `state.tsx`, `components.tsx`, and `src/pages/`.
- `frontend/e2e/workflows.spec.ts`, `e2e/nginx-smoke.mjs`, `playwright.config.ts`,
  `tests/browser_server.py`, Python unit/integration suites.
- Root README, Compose/Dockerfiles, `tests/compose.browser.yaml`, Python metadata/
  lock, frontend package metadata/lock and `.github/workflows/ci.yml`.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md and mdfiles/next-agent.md. Inspect Git status,
preserve unrelated work, verify prerequisites on updated main and inspect existing
T05 PR #11 before creating a task branch. Continue/review T05 only if outstanding;
if merged, follow its updated handoff for the next bounded assignment. Preserve
accounts, data and policy/version/audit/idempotency contracts. Explain the plan,
run checks, update handoff/contracts/map, and open a draft PR. Do not merge, advance
beyond the assigned task, publish repositories, activate providers or execute
arbitrary adopted repository code.
Retain the planned T09a Terraform foundation before T10; do not implement it now.
