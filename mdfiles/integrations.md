# GitHub Actions and Databricks integration

Status: T08 read-only GitHub capture/CI is implemented for review. Dispatch and
Databricks remain planned. Verify API/tool versions during each integration task;
T08 REST sources below were checked 2026-10-17; older sources date to 2026-09-11.

## T08 read-only boundary

API and worker require `GITHUB_READS_ENABLED=true` and a comma-separated or JSON
`GITHUB_ALLOWED_REPOSITORIES` list of exact `owner/repository` names (case-insensitive).
Defaults deny all reads. Restart processes after configuration changes. The optional
`GITHUB_READ_TOKEN` is resolved only from the worker process environment. Give it
Contents:read and Actions:read for explicitly authorized repositories. Public reads
can be unauthenticated. Do not add it to shared API configuration, payloads or bundles.
This feature does not change `RUNTIME_PROFILE=local` / `DEPLOYMENT_EXECUTOR=simulated`.

REST version `2026-03-10` is pinned. The adapter resolves a commit, persists its SHA
and numeric repository ID, checks repository identity again, downloads only that
SHA, and stores the inspected bundle root as a canonical ZIP. It reads only fixed
`api.github.com` and `codeload.github.com` origins; API redirects are rejected except
the expected zipball redirect to the same repository/SHA. Authorization is never
forwarded to the archive host; signed locations are never stored/logged. Each read
has a 10-second socket timeout, 30-second read deadline and 2 MB response limit.
Archives permit at most 500 entries / 2 MB declared expanded data, no traversal,
symlinks, encryption or duplicate paths; the selected canonical bundle has at most
50 files / 2 MB including ZIP metadata. `.git`, `.env`, `.aws`, `.ssh` bundle paths
are rejected. These are small-template limits, not general monorepo support.

CI reads use `head_sha`, fixed constructed pagination URLs and up to 10 pages/1000
runs. Mismatched commit/repository, duplicate attempts, changing totals or incomplete
pagination fail without publishing partial observations. Rate limits persist a
retry delay (at least 60 seconds, honoring provider headers up to one day) instead
of sleeping with database locks. Longer requested waits stop with a diagnostic.
Only three automatic execution attempts are allowed by the existing queue; manual
retry remains authorized and preserves any resolved commit. Read-only crash recovery
can safely retry; it never dispatches workflows or returns simulated provider results.

The separate CI overlay uses pinned checkout/setup-uv commits already used by this
repository, uv 0.12.11/Python 3.11, and its own checked-in tool lock. It is downloaded
and manually reviewed/applied at repository root, with the configured bundle path.
The v1 template remains byte-for-byte unchanged: onboarding documents its one-line
import-format migration, and CI builds a temporary package copy using pinned
setuptools. It runs locked installs, Ruff, mypy, unittest, structural checks and a
wheel build. It neither dispatches deployment nor receives workspace credentials.
PR checks may target a synthetic merge SHA; capture that exact SHA, or observe the
merged main push run. A genuine application CI demonstration remains unrun pending
separate authorization; the platform's own hosted CI does not satisfy that gate.

Primary references: [REST versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
[commit resolution](https://docs.github.com/en/rest/commits/commits#get-a-commit),
[ZIP archive redirect](https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-zip),
[workflow run filters](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository),
[rate-limit handling](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

## Generated application contract

```text
application-repository/
  databricks.yml
  resources/synthetic_job.yml
  src/<package>/
  tests/
  pyproject.toml
  uv.lock
  .github/workflows/ci.yml
  .github/workflows/deploy.yml
  README.md
```

Template inputs initially: application slug, package name, bundle target, approved
compute/resource references, and synthetic-output location. Validate identifiers
and paths. Do not allow arbitrary shell fragments, URLs, template source paths,
or inline secrets. Existing repository onboarding checks the bundle root and
contract; adding template/workflow files requires a reviewed PR, not overwriting
user code. T05 produces downloads; automated PR/repository creation is deferred.

Version templates by immutable content digest plus human-readable version. Define
a stable archive algorithm (ordered entries, normalized metadata, allowed files)
and test deterministic generation. Store a manifest with parameter/config digests
and tool versions. Never fetch dependencies implicitly during local generation.
Locked template dependencies are prepared and reviewed as template assets.

## Separate CI from deployment

- PR CI: locked dependency installation, Ruff, type checking, unit tests, package
  build and offline configuration checks. No workspace credentials, including on
  forks; no execution of untrusted code under `pull_request_target` privileges.
- Workspace validation: a separately authorized trusted workflow/operation with
  scoped identity. Offline validation is not proof of workspace validity.
- Deployment: explicit dispatch for an approved immutable revision and target;
  check out the exact application commit, validate, deploy the bundle, and publish
  a machine-readable result manifest. A workflow success flag alone is insufficient.
- Job execution: separate operation/run record; use a known deployed resource key,
  observe real termination, and verify the expected synthetic result.

Bundle commands are supported within CI/CD workflows; configuration and workflow
execution are different layers. See [Databricks CI/CD workflows](https://docs.databricks.com/aws/en/dev-tools/ci-cd/flows).

Use a separate CI workflow for this control-plane repository; it tests the API,
worker, migrations, and template generator. Do not confuse it with workflows
distributed into managed application repositories.

## Outbound-only GitHub adapter

The local worker calls GitHub's API; GitHub never needs a callback to localhost.
Use bounded timeouts, pagination, rate-limit-aware backoff, and a restricted
credential resolved outside operation payloads. Record repository, workflow ID,
trusted workflow ref, application commit, target, operation correlation ID,
external run ID/attempt, URL, conclusion, and observation time.

Workflow dispatch selects a branch/tag `ref`; source commit is a separate explicit
input verified by the workflow checkout. Do not assume dispatching a moving branch
deploys the approved application commit. The workflow file must satisfy GitHub's
default-branch requirements. Verify details against the
[workflow event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
and [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

Before dispatch, persist a stable correlation ID. Include it in inputs, run name,
and result manifest. Capture a run ID if the API returns one; otherwise discover
the matching run using workflow/repository/ref/time/correlation, with pagination.
Never choose merely the latest run. Record rerun attempt as well as run ID.

An HTTP timeout may mean dispatch succeeded. Reconcile before any resubmission;
no visible run yet is not proof of nonexecution. Duplicate matches or an expired
observation window require operator attention. Provider concurrency settings
supplement the DB reservation; do not use cancellation of an in-progress deployment
as the normal conflict-resolution strategy.

Result manifests must bind operation, application, exact commit/artifact, config
digest, target, mode, workflow run/attempt, external resource IDs, and outcome.
Reject mismatched manifests. A local artifact path is inaccessible to a hosted
runner: real deployment requires GitHub-accessible immutable source or an uploaded,
verified artifact. Initially use an approved repository commit. Capture the built
artifact digest before approval if the workflow introduces a separate build output.

## Approval and execution trust

T06 implements platform approval and worker rechecks. T09 first demonstrates
dispatch with a harmless workflow, without Databricks credentials.

T10's single-admin sandbox trusts the repository/workflow administrator. Someone
who can alter the privileged workflow, dispatch directly, or change credential
policy may bypass the local platform. Document that limit in the UI/demo and do
not call it organization-enforced approval. A dispatch input named `approved`
is never authorization evidence.

Before an organizational pilot, choose and test an enforcement design in ADR-007:
trusted centrally controlled deployment workflow, protected immutable deployment
request/approval evidence, and a gate bound to exact source/config/target before
credential acquisition. Address alternate dispatch paths, replay, revocation,
workflow edits, and the gap between approval and execution. Verify availability of
required GitHub protection features for the actual account/repository; no paid-plan
capability is assumed. This gate is required for a pilot, not for local simulation.

## Credentials, code execution, and Databricks

Restrict identities separately: GitHub polling/dispatch, Databricks deployment,
job runtime, and output storage. The API receives none of these credentials.
Do not run arbitrary repository hooks in the general worker. Capturing source and
checking metadata does not require executing source. Builds/tests/bundle execution
run in an isolated execution environment with approved templates, restricted
mounts/credentials, bounded time/resources, and argument-array subprocess calls.

Evaluate GitHub OIDC federation for the available Databricks account rather than
assuming a long-lived personal token is necessary. Federation requires explicit
provider policy setup and tightly scoped trust; see
[Databricks GitHub federation](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github).
Verify the Azure workspace's supported authentication and compute configuration
when one is available. No identity setup or paid execution is authorized by this
documentation task.

Register existing workspace/resources only. Select one supported compute option
after inspecting actual availability/costs; configure timeouts, limited concurrency,
and small synthetic inputs. No automatic schedule or production dataset. Real
job results must contain the provider run ID and verifiable output, not a fabricated
success payload. Do not claim simulated provisioning created real resources.

## Cost and availability policy

The default local demo runs with networking to providers disabled. Real GitHub
tests and Databricks tests are opt-in. Before activating them, document repository
visibility, Actions/runners/artifact limits, Databricks compute choice and billing
exposure, and how to stop resources. Do not publish code to obtain free usage or
promise free Databricks/Azure service. Rate/budget limits are operational controls,
not guaranteed hard spending caps unless verified for the actual service.

## T05 concrete local template

The implemented `backend/templates/python_batch_v1` template contains a minimal
bundle/target and synthetic notebook task, Python package, stdlib tests, manifest,
README, pyproject and uv lock. Its dependencies are empty; Python 3.11+ and uv
0.12.11 were selected from the existing toolchain. Package names are deliberately
restricted to `batch_...`; compute/resource/output-location inputs are deferred
rather than accepting arbitrary strings. Config uses the existing bounded synthetic
row count and timeout. No GitHub CI/deploy workflow, credentials, schedule or compute
provisioning is generated in T05; those require their later integration tasks.

Run `uv run --locked python scripts/check_generated_project.py` to install from the
generated lock in a fresh offline cache and run its tests in a disposable directory.
The worker only checks approved content and static syntax. This does not establish
Databricks bundle schema validity or workspace/compute readiness.

## T06 implemented simulation boundary

The only deployment executor is the explicit `local` / `simulated` combination.
Its closed success/partial-failure fixture emits `simulated://deployment/...`
references and `execution_mode=simulated` on every resource observation. It performs
no GitHub, Databricks, Terraform, source execution or infrastructure calls. The
approval binds offline evidence only; this cannot authorize a future real executor.
Adding real execution requires a new scope/policy and the later integration gates.
Local DB/host administrators remain trusted; this is not an organizational gate.

## T07 implemented run simulation boundary

The run adapter handles only `synthetic_job` with bounded synthetic row count and
explicit success/failure fixtures in local simulated mode. It does not import or
execute generated/adopted source, invoke a shell, schedule work or contact providers.
The fixed output is checked before successful fenced completion. Records carry
`execution_mode=simulated` and a null provider run ID. Real provider lifecycle/result
mapping and output retrieval remain T10 work; a simulation result does not satisfy
that gate or select a fake result for future real execution.
