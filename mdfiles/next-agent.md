# Agent handoff

Inspect Git status, preserve unrelated work, verify prerequisites on updated main,
and read AGENTS.md before creating or continuing a task branch. Leave merging to
the user. T11 is implemented for review; this handoff does not claim its PR is merged.

## Implemented state

T01–T07 are merged. T07 PR #15 merged at
`55105b71f31f033aa407f000c9f4a44238b09ef0` on 2026-09-27, verified through fetched
main and GitHub metadata on 2026-10-17. T11 starts from that main. The abandoned
T05 database, branch and stash were not changed. Historical migrations 001–010
remain unchanged and AI features remain removed.

T11 adds `011_platform_access` and own-access requests using existing platform
roles. Any active user with a known application ID can request one of the four
application roles. Requester identity is server-derived. Owner/admin decisions,
role insertion and audit share a transaction; identical decision replay never
recreates a revoked role. A partial unique index prevents duplicate pending
app/user/role requests. Requesters can withdraw pending requests and read their
own outcomes after revocation without gaining private application metadata.

React adds an own-request inbox, per-application owner/admin decisions, request
withdrawal and effective-access inspection. The latter explains direct/team roles,
owner/data-owner/admin relationships and inactive accounts. Role deletion stays
the existing audited command. Retained access is explicit and complete grant
revocation blocks API reads and queued work.

Owner/admin archive uses expected metadata version and rejects any nonterminal
operation or retained reservation. It cancels pending access requests with audit,
increments version and retains roles, artifacts, revisions, approvals, deployments,
runs and history. New app commands/grants are blocked. Role revocation remains
available to secure archived history; global team/environment policy stays separate.
No restore or external resource deletion is implemented. ADR-020 records the policy.

Application locks serialize lifecycle, role and access writes. Command/worker paths
acquire environment locks before the application lock and refresh current identity,
visibility and role eligibility after waits. Archive holds only the application
lock and reads unresolved work, closing the archive-versus-submit race without an
opposite operation/environment lock order. Queue reservation/fencing semantics
are unchanged. No dependencies or lockfile changes.

## Verification performed

Local checks on 2026-10-17:

- `uv run --locked pytest -q`: **213 passed**, including **23 access/archive cases**.
  Covers privacy/pagination, strict inputs, approval/self-escalation/replay,
  withdrawal/rejection, inactive subjects, transactional failure, retained team
  grants, complete revocation with worker denial, archive conflicts and preservation
  of recorded delivery/run results and downloadable artifacts.
- CI-scoped `ruff check` and `ruff format --check`: **81 files passed**.
  `uv run --locked mypy`: **48 modules passed**.
- `uv run --locked python scripts/check_generated_project.py`: locked offline
  installation and **2 generated stdlib tests passed**.
- `uv run --locked pytest tests/integration -q`: **28 skipped** because
  TEST_DATABASE_URL is unset. This is collection/skip evidence only. The five new
  PostgreSQL tests cover concurrent duplicate requests/decisions, both orderings
  of archive versus submission, changed ownership during a lock wait, migration
  preservation, pending uniqueness and refusal to downgrade with request history.
- Frontend lint, Prettier, TypeScript and production build passed using existing
  local Node 24.21.0/npm dependencies. All **13 Chromium workflows passed** (46.3s),
  including request/decision, retained team access, final revocation, stale and
  unresolved archive rejection, preserved audit and mobile overflow checks.
  Desktop retained-access and mobile archived-history screenshots were inspected.
- Python commands required execution outside the sandbox for uv cache locks.
  Tests used disposable SQLite data; no developer database was migrated. No global
  installation, real-provider work or infrastructure activation occurred.
- Docker's WSL launcher reports unavailable integration and ~/code/devstack is
  absent. Local PostgreSQL, container builds and production nginx smoke were not
  run in this session. Hosted T11 CI is pending; inspect actual results.

## Remaining work and limitations

- Review T11, ADR-020 and actual CI. PostgreSQL concurrency/migration behavior
  requires the hosted integration result; skipped tests do not satisfy that gate.
  Only the user merges. Execution remains explicitly local simulation.
- The abandoned T05 database reportedly uses `008_bundle_generation`, while main
  uses `008_prepared_revisions`. Do not stamp/reset/automatically migrate it.
  Preserve its data, abandoned branch and stash; conversion needs separate,
  inspected data-preserving work. Use an isolated database on the merged chain.
- Requests require a known application ID. There is no public application directory,
  notification delivery, global manager inbox, bulk ownership/admin removal,
  unarchive or external GitHub/Databricks/data permission change.
- Effective-access displays are current reads, not future guarantees. Team role
  removal affects all members; shared team membership changes remain admin-only.
  Owner/data-owner/admin relationships may retain reads after all roles are removed.
  Revocation does not undo work already executed; workers recheck before action.
- Global environment administration may still invalidate bindings of archived
  applications; archiving preserves histories, not a frozen external configuration.
- Existing limitations remain: local DB/host admins are trusted; logout does not
  revoke copied JWTs; artifacts need backups with the DB; offline validation is
  not workspace validation. There is no real compute, scheduling or provider result.

## Next task

Review T11 and its actual checks, resolving failures before merge. After user merge
and a separate assignment, implement **T08 only**: adopt an existing GitHub repo,
asynchronous exact source capture and CI observations, plus reviewed generated CI
files/onboarding. Follow T08 exclusions; no repository creation, automatic commits,
credential activation, deployment or paid jobs. A genuine external CI demonstration
requires separate authorization. T09/T10 and Terraform remain separate work.

## Files to read first

- AGENTS.md; mdfiles/README.md; T11/T08 in development-plan.md; next-agent.md.
- mdfiles/domain-contracts.md, api-contracts.md, architecture.md; ADR-020 in decisions.md.
- backend/models/access.py, access_schemas.py; migration 011_platform_access.py.
- backend/services/access_service.py, policy_service.py, application_service.py;
  environment/delivery/deployment/job_run/operation service command guards.
- backend/api/endpoints/access.py, applications.py; frontend/src/pages/access.tsx,
  applications.tsx and App.tsx.
- tests/unit/test_access.py; tests/integration/test_access.py, test_migrations.py;
  frontend/e2e/workflows.spec.ts; .github/workflows/ci.yml.
- For T08: mdfiles/integrations.md, existing immutable revision/artifact/template
  services and durable worker contracts. Read affected code before implementation.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md, next-agent.md and the T08 contracts. Inspect Git
status and preserve unrelated work, the abandoned T05 branch/stash and its old
008_bundle_generation database. Verify T11 is reviewed and merged on updated main
before implementing separately assigned T08 on its own branch. Build only existing
GitHub repository adoption, asynchronous immutable source capture and exact-commit
CI observations with mocked failure coverage and a React UI. Preserve lifecycle
locking, current authorization and durable operation contracts. Use isolated test
data, record actual checks and update the handoff. Leave merging to the user; do
not activate providers, create repositories or convert the old database.
