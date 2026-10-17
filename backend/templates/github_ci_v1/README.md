# Reviewed Python batch CI onboarding

These files are an optional overlay for an existing repository. They do not change
the immutable python-batch:1.0.0 template or its recorded digest.

1. Review every file before copying this archive into the **repository root**.
   Resolve existing workflow/tooling conflicts manually; do not overwrite blindly.
2. The configured bundle root is `__BUNDLE_ROOT__`. It must contain the approved
   generated manifest, `databricks.yml`, `pyproject.toml`, `uv.lock`, `src/`, and tests.
   The manifest's target and config must match the selected control-plane binding.
   Source changes are allowed; the captured artifact digest identifies actual bytes.
   The immutable v1 template predates Ruff's import-order checks. Before enabling
   CI, run `uv run --locked --project .control-plane-ci ruff check --isolated --fix <bundle-root>/src <bundle-root>/tests`,
   review the one blank-line import fix in `tests/test_batch.py`, and commit it.
   CI itself only checks files; it does not fix or commit them.
3. Commit the reviewed overlay on a branch and open a pull request. Enable Actions
   only after reviewing repository billing/settings and trust. The workflow runs
   on GitHub-hosted runners with contents:read, no persisted checkout credentials,
   no secrets, no pull_request_target, and no Databricks access. Do not use a runner
   with internal credentials or network access for untrusted repository code.
4. CI installs the separately locked tool environment and application dependencies,
   runs Ruff, strict mypy on src, unittest, static checks, and a wheel build. The v1
   package=false project is built in a temporary copy using pinned setuptools.
   Custom build backends require a separately reviewed workflow. These checks run
   repository code in Actions; the control-plane worker never executes that code.
5. After an authorized CI run, capture its exact commit in the control plane and
   choose Refresh CI. Pull-request checks may use GitHub's synthetic merge commit;
   capture that SHA to observe those checks, or capture the merged main commit
   after its push workflow. Never substitute the latest branch run for an exact SHA.
6. CI observations are informational, including failed/cancelled/skipped runs and
   rerun attempts. They do not grant deployment approval or workspace validity.
   Refresh again after a run finishes; historical observations remain immutable.

An administrator must separately configure GITHUB_READS_ENABLED=true and the
owner/repository allowlist GITHUB_ALLOWED_REPOSITORIES on API and worker. The
worker alone may receive GITHUB_READ_TOKEN with Contents:read and Actions:read for
the selected repository. Public repositories can use unauthenticated reads.
Never put credentials in a bundle, command payload, repository, or downloaded files.
This download does not enable provider access, install a workflow, or trigger CI.
