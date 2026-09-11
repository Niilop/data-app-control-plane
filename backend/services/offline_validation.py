"""Offline checks of a captured artifact. Nothing here contacts a workspace.

These checks parse and inspect the stored archive. They never execute generated
code, never resolve or download dependencies, and never call a provider. Passing
them is evidence that the captured artifact is internally consistent and safe to
extract; it is explicitly **not** evidence of workspace validity, of a successful
`databricks bundle validate`, or of deployability. Do not relabel it as such.
"""

import ast
import re
import sys
import tomllib
from datetime import datetime, timezone
from typing import Any

from models.environment_schemas import SafeBindingConfig
from services.template_service import GenerationError, read_archive

VALIDATOR = "control-plane-offline"
VALIDATOR_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = 1
LIMITATIONS = (
    "Offline scope only: no Databricks workspace, cluster, credential or network"
    " was contacted.",
    "No generated code was executed; Python files were parsed, not run.",
    "Dependencies were not resolved or installed; the lock file was only parsed.",
    "This is not a workspace validation and must not be recorded or displayed as one.",
)


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def _significant(text: str) -> str:
    """Drop YAML comments and blank lines so checks read configuration, not prose.

    Without this, a comment explaining why the file avoids `pull_request_target`
    would itself fail the check that looks for that trigger.
    """
    lines = [
        cleaned
        for line in text.splitlines()
        if (cleaned := re.sub(r"(?:(?<=\s)|^)#.*$", "", line).rstrip())
    ]
    return "\n".join(lines)


def _syntax_checks(entries: dict[str, bytes]) -> dict:
    sources = sorted(name for name in entries if name.endswith(".py"))
    if not sources:
        return _check("python_syntax", False, "The archive contains no Python sources")
    for name in sources:
        try:
            # Parsing only. ast.parse never evaluates the module.
            ast.parse(entries[name].decode("utf-8"), filename=name)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            return _check("python_syntax", False, f"{name} is not valid Python")
    return _check(
        "python_syntax", True, f"{len(sources)} Python files parsed without executing"
    )


def _project_checks(entries: dict[str, bytes], package: str) -> list[dict]:
    checks = []
    try:
        project = tomllib.loads(entries["pyproject.toml"].decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError):
        return [
            _check(
                "project_metadata", False, "pyproject.toml is missing or unparsable"
            ),
            _check("dependency_lock", False, "Project metadata could not be read"),
        ]
    metadata = project.get("project", {})
    declared = metadata.get("dependencies", None)
    checks.append(
        _check(
            "project_metadata",
            metadata.get("name") == package and declared == [],
            "Project declares the expected package name and no third-party dependencies"
            if metadata.get("name") == package and declared == []
            else "Project name or dependency list does not match the generated package",
        )
    )
    try:
        lock = tomllib.loads(entries["uv.lock"].decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError):
        checks.append(
            _check("dependency_lock", False, "uv.lock is missing or unparsable")
        )
        return checks
    locked = sorted(item.get("name", "") for item in lock.get("package", []))
    expected = [package.replace("_", "-")]
    consistent = locked == expected and lock.get("requires-python") == metadata.get(
        "requires-python"
    )
    checks.append(
        _check(
            "dependency_lock",
            consistent,
            "Lock file pins only the project itself and matches its Python requirement"
            if consistent
            else f"Lock file contents are unexpected: {locked}",
        )
    )
    return checks


def _bundle_checks(entries: dict[str, bytes], revision: dict) -> list[dict]:
    """Structural text checks of the generated bundle files, not a bundle validation."""
    checks = []
    try:
        bundle = _significant(entries["databricks.yml"].decode("utf-8"))
        job = _significant(entries["resources/synthetic_job.yml"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError):
        return [
            _check("bundle_structure", False, "Bundle definition files are missing"),
            _check("job_configuration", False, "Job definition file is missing"),
        ]
    slug, target = revision["application_slug"], revision["bundle_target"]
    bundle_ok = (
        f"name: {slug}" in bundle
        and f"  {target}:" in bundle
        and "include:" in bundle
        and "resources/*.yml" in bundle
    )
    checks.append(
        _check(
            "bundle_structure",
            bundle_ok,
            f"Bundle names {slug} and declares target {target}"
            if bundle_ok
            else "Bundle definition does not declare the recorded slug and target",
        )
    )
    config = revision["config_snapshot"]
    scheduled = any(
        keyword in job
        for keyword in ("schedule:", "schedules:", "continuous:", "trigger:")
    )
    job_ok = (
        "max_concurrent_runs: 1" in job
        and f"timeout_seconds: {config['max_runtime_seconds']}" in job
        and f'"{config["synthetic_row_count"]}"' in job
        and not scheduled
    )
    checks.append(
        _check(
            "job_configuration",
            job_ok,
            "One concurrent run, the recorded timeout and row count, and no schedule"
            if job_ok
            else "Job definition does not match the recorded configuration,"
            " or declares an automatic trigger",
        )
    )
    return checks


def _workflow_checks(entries: dict[str, bytes]) -> dict:
    try:
        ci = _significant(entries[".github/workflows/ci.yml"].decode("utf-8"))
        deploy = _significant(entries[".github/workflows/deploy.yml"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError):
        return _check("workflow_safety", False, "Workflow files are missing")
    unsafe = []
    if "pull_request_target" in ci:
        unsafe.append("CI uses pull_request_target")
    if "secrets." in ci:
        unsafe.append("CI references repository secrets")
    if "on:\n  workflow_dispatch:" not in deploy:
        unsafe.append("Deployment workflow is not dispatch-only")
    for name, text in (
        (".github/workflows/ci.yml", ci),
        (".github/workflows/deploy.yml", deploy),
    ):
        if "permissions:\n  contents: read" not in text:
            unsafe.append(f"{name} does not restrict permissions to contents: read")
    return _check(
        "workflow_safety",
        not unsafe,
        "CI runs without secrets and deployment is manual dispatch only"
        if not unsafe
        else "; ".join(unsafe),
    )


def validate_offline(content: bytes, revision: dict) -> dict:
    """Run every offline check over the captured archive and build its report."""
    checks: list[dict] = []
    entries: dict[str, bytes] = {}
    notes: list[str] = []
    try:
        entries = read_archive(content)
        checks.append(
            _check(
                "archive_entries",
                True,
                f"{len(entries)} entries are regular files with safe relative paths",
            )
        )
    except GenerationError as error:
        checks.append(_check("archive_entries", False, error.code))
    if entries:
        required = revision["required_targets"]
        missing = [name for name in required if name not in entries]
        checks.append(
            _check(
                "required_files",
                not missing,
                "Every file required by the template contract is present"
                if not missing
                else f"Missing: {', '.join(missing)}",
            )
        )
        package = revision["package_name"]
        checks.extend(_project_checks(entries, package))
        checks.append(_syntax_checks(entries))
        checks.extend(_bundle_checks(entries, revision))
        checks.append(_workflow_checks(entries))
        expected_sources = [
            f"src/{package}/__init__.py",
            f"src/{package}/main.py",
            f"src/{package}/synthetic.py",
        ]
        present = [name for name in expected_sources if name in entries]
        checks.append(
            _check(
                "package_layout",
                len(present) == len(expected_sources),
                f"src/{package}/ contains the generated modules"
                if len(present) == len(expected_sources)
                else "Generated package layout is incomplete",
            )
        )
    try:
        SafeBindingConfig.model_validate(revision["config_snapshot"])
        checks.append(
            _check(
                "configuration_bounds",
                True,
                "Captured configuration is inside the closed schema's bounds",
            )
        )
    except ValueError:
        checks.append(
            _check(
                "configuration_bounds",
                False,
                "Captured configuration is outside the supported schema",
            )
        )
    if revision.get("policy_drift"):
        notes.append(
            "Environment or binding policy has changed since this revision was"
            " captured; recorded eligibility must be re-established before approval."
        )
    result = "passed" if all(check["passed"] for check in checks) else "failed"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "scope": "offline",
        "validator": VALIDATOR,
        "validator_version": VALIDATOR_VERSION,
        "tool_versions": tool_versions(),
        "revision_id": revision["revision_id"],
        "application_id": revision["application_id"],
        "artifact_digest": revision["artifact_digest"],
        "template": revision["template"],
        "scope_digest": revision["scope_digest"],
        "result": result,
        "checks": checks,
        "notes": notes,
        "limitations": list(LIMITATIONS),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def tool_versions() -> dict[str, Any]:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}",
        "validator": VALIDATOR_VERSION,
    }


def summarise(report: dict) -> dict:
    """A small, safe summary for list views; the report artifact holds the detail."""
    return {
        "result": report["result"],
        "passed": sum(1 for check in report["checks"] if check["passed"]),
        "total": len(report["checks"]),
        "failed": [check["name"] for check in report["checks"] if not check["passed"]],
    }
