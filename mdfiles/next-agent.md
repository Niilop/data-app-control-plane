# Agent handoff

Inspect Git status, preserve unrelated work, verify prerequisites on updated main,
and read AGENTS.md before creating or continuing a task branch. Leave merging to
the user. T08 is implemented for review; this handoff does not claim it is merged.
Draft PR: https://github.com/Niilop/data-app-control-plane/pull/17.

## Implemented state

T01–T07 and T11 are merged. T11 PR #16 merged at
`3671334aee3ff964d7f233313c63314db7c3b747` on 2026-10-17, verified through fetched
main and GitHub metadata. T08 starts from that main. The abandoned T05 database,
branch and stash remain untouched; migrations 001–011 and v1 template assets are
unchanged. AI features remain removed.

T08 adds migration `012_github_source`, SourceCapture, append-only CIRun history,
and durable `capture_github` / `refresh_github_ci` operations with `github_read` mode.
Explicit GitHub reads and exact repository allowlist default off. Only the worker
reads the optional GITHUB_READ_TOKEN environment variable; commands/responses/audits
contain no credentials or signed archive URLs. Deployment remains simulated.

Source commands require current developer access and binding version. The worker
checks policy, resolves repository/ref, commits repository ID/SHA under a lease
fence, then downloads that exact SHA. Automatic/manual retry preserves the pin.
Archive inspection is bounded and in memory, with no source execution. Completion
rechecks current actor/repository/root/template/binding and cancellation; source,
artifact association, repository verification time, operation/reservation and audit
commit under the fence. Adopted revisions reuse immutable offline validation and
simulated approval/deployment behavior. CI observations are informational, tied to
exact commit/run/attempt, and appended by explicit queued refreshes. API GETs never
fan out to GitHub. Pagination failures do not publish partial observations.
Accepted CI-refresh command replay rechecks current application access/lifecycle
before returning its existing operation, even after the binding version changes;
a new refresh still rejects stale source configuration. Its regression was observed
failing before the fix and passing afterward.

React shows disabled access, capture status/diagnostics, commit/time, revision
capture and recorded CI results. A separate downloadable CI overlay contains pinned
actions, its own tool lock, Ruff/mypy/unit/static checks and wheel build. It is
manually reviewed/applied; no repository writes or workflow dispatch. Immutable v1
templates predate Ruff import ordering and use package=false: onboarding documents
a one-time blank-line fix and CI builds a temporary package copy. ADR-021 records
the design. No runtime dependencies or root lockfile changes.

## Verification performed

Local checks on 2026-10-17:

- `uv run --locked pytest -q`: **261 passed**, including **44 GitHub cases** covering
  command denial, manual retry pins, unstable pagination, malformed archives,
  current policy and cancellation.
- `uv run --locked mypy`: **55 modules passed**. All CI-scoped Ruff lint and format
  checks passed (85 existing/expanded files plus 8 new source/CI files).
- All **14 Chromium workflows passed** using disposable API/SQLite and a test-only
  scripted GitHub adapter. Includes failed source diagnostics, adoption/revision,
  exact-commit failed CI observations, repeated refresh keys and narrow viewport.
  A small verification-time display/screenshot follow-up also passed the focused
  adoption rerun. The full mobile screenshot was inspected with no overflow.
- Frontend lint, format, TypeScript and production build passed.
- `scripts/check_ci_onboarding.py` passed locked tooling installation, the documented
  reviewed one-blank-line migration, Ruff, mypy, 2 unittest cases and wheel build.
- PostgreSQL source/migration selection collected with **8 skips** because
  TEST_DATABASE_URL is unset. No developer database was migrated. Hosted evidence
  below supplies PostgreSQL/container verification; skips are not counted as passes.
- Browser binaries were downloaded to /tmp, not globally. uv cache access and test
  server startup required sandbox escalation. No provider credentials were activated,
  application workflow run, infrastructure deployed or paid workload started.

Hosted [Platform CI 39039496527](https://github.com/Niilop/data-app-control-plane/actions/runs/39039496527)
passed all jobs at `332f36761a2d46215abfb75b5aa7175153b32c5b`:
**261 offline tests, 31 PostgreSQL tests with no skips, and 14 Chromium workflows**.
Ruff lint/format (93 files), mypy (55 modules), unchanged generated-project locked
offline installation/tests, and the new CI overlay installation/lint/types/unit/
wheel-build check passed. Locked frontend/browser images and production nginx smoke
passed routing, CSP, cookie login/reload, authenticated write, readiness and logout.
The first PostgreSQL run found a test-only active read transaction before queue claim;
the corrected test then exercised recovery and downgrade refusal successfully.

At `06f80ea`, the later accepted-CI-refresh replay fix passed all 44 focused GitHub
tests, Ruff and mypy locally, plus hosted offline and PostgreSQL jobs in
[run 39039632922](https://github.com/Niilop/data-app-control-plane/actions/runs/39039632922).
Its frontend is unchanged from the fully passing run above. This evidence update
changes documentation only; inspect the latest PR check status before merge.
The local handoff checker and `git diff --check` passed.

## Remaining work and limitations

- Review the T08 draft PR and inspect hosted results,
  especially migration/schema parity, PostgreSQL fencing and immutable history.
  Only the user merges. A genuine application-repository GitHub CI demonstration
  remains pending separate authorization; platform CI does not satisfy that gate.
- Adoption supports the approved Python batch v1 manifest/structure and matching
  target/config. It allows changed source bytes but is not a general repository
  build/import service. Limits: 2 MB archive/expanded content, 500 entries, 50 files
  in the selected canonical bundle. No YAML/workspace semantic validation.
- CI observations append historical snapshots; zero-run refresh is visible through
  operation/audit count. They do not enforce deployment approval or assert ongoing
  access. PR CI may run a synthetic merge SHA; capture that exact SHA or a merged
  main push commit. No webhook, workflow dispatch, repository creation or write API.
- HTTP reads are bounded; rate limits persist retry delays. Repository allowlist
  and flag changes require API/worker restart. Tokens belong in worker-only process
  configuration, not the shared Compose/API env file. No token supplied in this work.
- The abandoned T05 DB reportedly uses `008_bundle_generation`; current history
  uses `008_prepared_revisions`. Do not stamp/reset/migrate it automatically. Preserve
  its data, old branch and stash; conversion needs separate inspected work.
- Local host/DB admins remain trusted. JWT logout does not revoke copied tokens;
  artifact backups must accompany database backups. No real compute or provider
  deployment exists. PostgreSQL/devstack and local Docker were unavailable here.

## Next task

Review T08 and its actual checks; resolve failures before merge. After user merge
and a separate assignment, T09 adds dispatch/reconciliation of a harmless GitHub
workflow. It must remain distinct from deployment success and needs task-specific
provider authorization. Do not implement T09/T10 or convert the old database as a
side effect of reviewing T08. The separately authorized real T08 CI gate can be
demonstrated using the reviewed onboarding overlay on an existing repository.

## Files to read first

- AGENTS.md, mdfiles/README.md, development-plan.md T08, and this handoff.
- mdfiles/integrations.md, domain-contracts.md, api-contracts.md and ADR-021.
- backend/models/source.py, source_schemas.py, delivery.py and migration 012.
- backend/integrations/github.py, source_archive.py; services/source_service.py,
  delivery_service.py, queue_service.py and worker.py.
- backend/api/endpoints/sources.py; services/ci_onboarding.py and templates/github_ci_v1/.
- frontend/src/pages/sources.tsx, preparation.tsx and state.tsx.
- tests/unit/test_github_source.py, tests/integration/test_github_source.py,
  test_migrations.py, frontend/e2e/workflows.spec.ts, scripts/check_ci_onboarding.py.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md, next-agent.md and T08 contracts. Inspect Git status
and current PR/main state; preserve unrelated work, the abandoned T05 branch/stash
and its old database. Review source pins, current policy, safe archive/HTTP boundaries,
CI observation identity, migration/history guards and generated onboarding. Verify
the handoff against actual checks and hosted PostgreSQL evidence. Fix findings within
T08 on its task branch and update docs. Leave merge to the user; no provider activation,
repository writes, paid jobs, T09 dispatch or old database conversion is authorized.
