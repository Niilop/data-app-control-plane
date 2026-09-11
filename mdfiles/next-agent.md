# Agent handoff

Inspect Git status, preserve unrelated changes, verify prerequisites on updated
main, and read AGENTS.md before creating the next task branch. This handoff records
implementation; it does not imply that its PR has merged.

## Implemented state

T01–T04a are merged. T04a PR #10 was confirmed merged at
`6503ec152a7bcfbb3310e45c08f5fab78dea27d6`. T05 is implemented from that main on
branch `feat/t05-bundle-generation` and awaits review/merge. T06 has not started.
AI/chat/RAG/LLM/inference remain removed; historical tables and all migrations
through the new head `008_bundle_generation` are retained.

The platform continues to provide development accounts/admin bootstrap, teams,
owned applications, direct/team roles, versioned metadata, simulated environment
bindings, filtered paginated reads, transactional audit, browser sessions, and a
separate PostgreSQL worker with durable operations, reservations, idempotent
commands, leases/fencing, heartbeats, bounded retry, cancellation and reconciliation.

T05 adds deterministic generation, local artifacts, immutable revisions and
explicitly offline validation:

- One reviewed template, `python-batch 1.0.0`, under
  `backend/templates/python-batch/1.0.0/` (inside `backend/` so the existing image
  and dev bind mount carry it). A `template.json` manifest declares metadata,
  pinned tool versions, the parameter contract, required files and an explicit
  source-to-target allowlist. Assets use `@@name@@` placeholders, chosen so they
  cannot collide with `${var.x}` bundle or `${{ }}` Actions syntax.
- Generation is byte-reproducible: entries sorted by target path, fixed
  1980-01-01 timestamp, fixed `0644` mode and Unix create-system, and **stored
  uncompressed** so the digest does not depend on the machine's zlib version. The
  template's identity is a content digest over its manifest plus every asset; a
  registered version whose assets change is refused, not silently regenerated.
- Client input is two fields: `package_name` and `synthetic_output_path`. Slug
  comes from the registry, bundle target from the binding, and row count/timeout
  from the T03 binding configuration. The payload has no credential, command, URL,
  target or template-path field, and unknown fields are rejected.
- `integrations/artifact_store.py` stores content at `sha256/<aa>/<bb>/<digest>`
  under the absolute `ARTIFACT_DIR` (default `<DATA_DIR>/artifacts`), writes
  atomically, deduplicates identical content, and re-hashes on every read so a
  mismatch is refused rather than served. Compose mounts the same directory into
  the API **and** the worker; the worker previously had no data mount.
- Revisions are written once and never updated, capturing artifact digest,
  template version, binding/environment policy, configuration, `config_digest` and
  the `scope_digest` T06 must bind to and recheck. No edit route exists, so
  `PATCH`/`PUT`/`DELETE` return 405. Identical inputs reproduce the same scope
  digest; any change produces a new revision with a different one.
- Offline validation runs through the existing worker and writes an append-only
  result plus a JSON report artifact. Checks parse only: `ast.parse` for Python,
  `tomllib` for `pyproject.toml`/`uv.lock`, and comment-stripped structural reads
  of the bundle and workflow files. `ValidationResult.scope` is constrained to
  `offline` by the database, and every report copy states that no workspace,
  cluster, credential or network was contacted, no generated code was executed and
  no dependency was installed. The **operation** succeeds when the check runs;
  whether the artifact passed is the separate validation result, surfaced as a
  `validation_failed` diagnostic.
- Generation and validation carry `execution_mode="local"` — real work this
  machine performs — never `simulated`, which stays reserved for work standing in
  for a provider. A database check constraint enforces the kind/mode pairing in
  both directions. They take **no** binding reservation, so they never block a
  probe or future deployment on that binding, and `POST /operations/{id}/retry`
  returns 409 `unsupported_retry` for them (retry runs under operator authority,
  while these are developer actions; submitting a new request is equivalent
  because generation is deterministic). The worker rechecks the role each kind
  requires, so a revoked developer grant fails the operation with
  `authorization_changed` and writes no artifact.
- Handlers keep the T04 shape: read in a short transaction, compute outside one,
  then return result rows as an `apply` callback that `queue_service.finish` runs
  inside the fenced result transaction, so a lost lease discards them.
- The generated project is **stdlib-only by design**: no third-party runtime or
  test dependencies, so `uv sync --locked` and its `unittest` suite run with no
  network at all. Its bundle `spark_version`/`node_type_id` variables have no
  defaults, forcing an explicit workspace-verified value. Its deploy workflow is
  dispatch-only and fails before any bundle command until a repository
  administrator sets `DEPLOYMENT_ENABLED`.
- React adds **Bundles** and **Revisions** tabs: template catalogue, generation
  dialog, artifact table with real downloads, capture dialog with optional config,
  revision snapshot with digests, validation results and an offline disclaimer.
  Controls follow `capabilities`; the API remains authoritative.
- New API rows: `GET /templates`, `POST /applications/{id}/generations`,
  `GET /artifacts/{digest}`, `POST|GET /applications/{id}/revisions`,
  `GET /revisions/{id}`, `POST|GET /revisions/{id}/validations`, plus supporting
  `GET /applications/{id}/artifacts`. See ADR-017 for the decisions taken.

## Verification performed

On 2026-09-12, from branch `feat/t05-bundle-generation`:

- `uv run --locked pytest -q`: **188 passed** with network blocking enabled
  (125 previously + **63 new** delivery cases). Existing assertions and migration
  history are unchanged.
- `uv run --locked pytest tests/integration -q`: **23 passed** (15 previously +
  **8 new**), with no skips, against a throwaway `pgvector/pgvector:pg16`
  container created for this run on port 55439 and **removed afterwards**. It was
  not the developer's application database or a shared service.
- Ruff lint and format passed across the updated README/CI scope: **61 files**.
  `uv run --locked mypy`: **36 source files passed**.
- `uv run --locked python scripts/check_generated_project.py` passed: the archive
  was byte-identical across two renders, `uv sync --locked --offline` resolved,
  the generated project's **7 unittest cases passed**, and its CLI wrote the
  expected CSV. This is the acceptance check for installing from the lock, and it
  is now a CI step.
- Frontend: `npm run typecheck`, `lint`, `format:check` and `build` passed.
  **11 Chromium browser workflows passed** (9 previously + **2 new**) in
  `tests/Dockerfile.browser` against a disposable real FastAPI/SQLite API. The new
  ones verify the template catalogue, a real artifact download re-hashed in the
  browser against its recorded digest, a 202 generation labelled `local`, the
  revision snapshot and scope digest, the offline validation result and
  disclaimer, 405 on revision edit attempts, and viewer denial (403) for both
  generation and validation.
- The isolated production nginx/browser smoke passed: routing, CSP, cookie login
  and reload, authenticated write, worker readiness and logout.
- Local Docker Compose: quiet config validation, all images rebuilt, and
  `alembic upgrade head` applied **008** to the existing bundled database. A
  read-only check before and after confirmed the **2 existing accounts and every
  historical table are preserved**; the four new tables were added and the head is
  `008_bundle_generation`. `.env` and the database volume were untouched and never
  printed. `/ready` returned ready on both `localhost:8000` and `localhost:8501`.
  The four services remain running, as they were at session start.
- The shared artifact mount was verified directly: the **worker** container wrote
  an artifact and the **backend** container read the identical bytes back, then
  the probe file was deleted. Both containers resolve `ARTIFACT_DIR` to
  `/app/data/artifacts` and load the same template content digest.
  `GET /api/v1/templates` and `GET /api/v1/artifacts/...` return 401 unauthenticated.

**Not run.** No hosted CI run exists for this branch yet — inspect it before merge
and do not treat the local results above as CI evidence. No interactive UI journey
was performed against the developer's own database: no team, application, binding
or artifact was created there, so the end-to-end screen flow is covered by the
browser tests rather than by a manual walkthrough. Firefox and WebKit were not
tested. No repository was published, no provider was contacted, and no paid or
external workload ran.

## Remaining work and limitations

- Review T05 and its hosted CI before merge; it is **not** claimed merged. T06
  must wait for that merge.
- Offline validation is exactly that. It proves the captured artifact is
  internally consistent and safe to extract. It is **not** `databricks bundle
  validate`, not evidence of workspace validity or deployability, and must never
  be relabelled as workspace validation. There is no workspace scope in the code,
  the schema or the UI, and the database constraint should stay that way.
- The structural bundle and workflow checks are text reads of files this platform
  itself generated, after stripping comments. They are consistency and tamper
  checks, not a YAML schema validation; no YAML parser is a dependency. If the
  template grows, consider whether a real parser is warranted.
- Retry is refused for generation and validation rather than re-authorized under a
  different role. That follows the written permission model (recovery is an
  operator action, these are developer actions) but is a rough edge: a developer
  whose generation fails must submit a new request. If a future task introduces
  per-kind recovery roles, revisit this together with the domain contract.
- A generation's binding policy is rechecked by the worker, but its binding
  *version* is not pinned the way execution pins it, because generation only reads
  the application's own recorded state. Revisions do capture and can assert the
  version. Policy drift between capture and validation is recorded as a report
  note, not a failure; eligibility rechecking belongs to approval in T06.
- Adding any third-party dependency to the template loses the fully offline
  install-and-test property that `scripts/check_generated_project.py` relies on.
  Re-lock and re-verify that script if the template's dependencies ever change.
- The template's Databricks compute is deliberately unresolved. No workspace,
  runtime version, node type or cost has been verified, and nothing here should be
  read as a claim that the generated bundle deploys or runs.
- Artifacts live in a configured local directory. Moving hosts requires migrating
  it; there is no shared or remote artifact storage, no retention policy, and no
  cleanup of artifacts belonging to superseded revisions.
- Everything inherited from T04/T04a still applies: development logout does not
  revoke copied JWTs before expiry; recovery keys are cleared by a full reload;
  ownership controls still use user IDs; unknown probe outcomes retain their
  reservations; `~/code/devstack` is still absent and unverified.
- No approval, deployment, provider adapter, repository publication, source
  capture or organization identity exists.

## Next task

After confirming T05 is merged on updated main, implement **T06 — Approve and
simulate one deployment** on its own branch. Read the complete task and its
contracts first. Approval must bind to the exact `scope_digest` a revision already
records and to the accepted validation result, and must be rechecked — along with
current binding/environment policy and the actor's current roles — before the
worker performs a simulated deployment. Preserve the immutability of revisions and
validation results, the audit and idempotency contracts, and the `local` versus
`simulated` execution-mode distinction. Do not begin T07, publish repositories,
deploy real bundles, execute adopted repository code, or activate providers.

## Files to read first

- `AGENTS.md`, `mdfiles/README.md`, T06 in `mdfiles/development-plan.md`, and
  ADR-009/ADR-014/ADR-017 in `mdfiles/decisions.md`.
- Approval/deployment rules in `mdfiles/domain-contracts.md`, the T05 and T06 rows
  and "T05 implemented details" in `mdfiles/api-contracts.md`,
  `mdfiles/architecture.md` and `mdfiles/repository-map.md`.
- `backend/services/delivery_service.py` (especially `revision_scope` and
  `POLICY_VERSION`), `operation_service.py`, `queue_service.py`, `worker.py`.
- `backend/models/delivery.py`, `delivery_schemas.py`, `operations.py`,
  `operation_schemas.py`, and `backend/api/endpoints/delivery.py`.
- `backend/services/offline_validation.py` and `template_service.py` for what an
  offline result does and does not establish.
- `frontend/src/pages/delivery.tsx`, `applications.tsx`, `api.ts`, `types.ts`.
- `tests/unit/test_delivery.py`, `tests/integration/test_delivery.py`,
  `frontend/e2e/workflows.spec.ts`, `tests/browser_server.py`.
- Root README, `docker-compose.yaml`, `backend/alembic/versions/008_bundle_generation.py`,
  `scripts/check_generated_project.py` and `.github/workflows/ci.yml`.

## Suggested agent prompt

Read AGENTS.md, mdfiles/README.md and mdfiles/next-agent.md. Inspect Git status,
preserve unrelated work, verify T05 is merged into updated main, and create the
next task branch if needed. Implement T06 only: append-only approval bound to a
revision's exact recorded scope digest and accepted validation result, rechecked
with current policy and roles before a simulated deployment through the existing
durable worker, with its React screen. Preserve accounts, data, immutable
revisions and validation results, and the policy/version/audit/idempotency
contracts and the local-versus-simulated labelling. Explain the plan, run checks,
update handoff/contracts/map, and open a draft PR. Do not merge, start T07,
publish repositories, activate providers or execute arbitrary adopted code.
