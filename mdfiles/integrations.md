# GitHub Actions and Databricks integration

Status: planned. Verify API/tool versions and provider capabilities during each
integration task; pin the versions tested. Sources below were consulted 2026-09-11.

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
