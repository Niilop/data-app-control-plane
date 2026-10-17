"""Reviewed CI runner for Python batch repositories. Never imported by the worker."""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    root = Path(os.environ.get("BUNDLE_ROOT", ".")).resolve()
    project = tomllib.loads((root / "pyproject.toml").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["template_id"] == "python-batch:1.0.0"
    assert (root / "databricks.yml").is_file()
    for folder in ("src", "tests"):
        for path in (root / folder).rglob("*.py"):
            ast.parse(path.read_bytes())
    # The tooling environment and application's dependencies have separate locks.
    # Ignore the tool environment's VIRTUAL_ENV while syncing the application.
    os.environ.pop("VIRTUAL_ENV", None)
    run("uv", "sync", "--locked", "--no-dev", "--project", str(root), cwd=root)
    run(sys.executable, "-m", "ruff", "check", "--isolated", "src", "tests", cwd=root)
    run(sys.executable, "-m", "mypy", "--strict", "src", cwd=root)
    run(
        "uv",
        "run",
        "--locked",
        "--no-dev",
        "--project",
        str(root),
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
        cwd=root,
    )
    # Immutable v1 bundles intentionally have package=false and no build backend.
    # Build a copy with pinned setuptools; never edit the checked-out project/lock.
    with tempfile.TemporaryDirectory(prefix="batch-build-") as temporary:
        stage = Path(temporary)
        shutil.copytree(root / "src", stage / "src")
        text = (root / "pyproject.toml").read_text()
        if "build-system" not in project:
            text += '\n[build-system]\nrequires = ["setuptools==80.9.0"]\nbuild-backend = "setuptools.build_meta"\n'
            text += '\n[tool.setuptools.packages.find]\nwhere = ["src"]\n'
        else:
            raise ValueError(
                "Review a custom build backend separately before enabling this v1 CI runner"
            )
        (stage / "pyproject.toml").write_text(text)
        run(
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            str(stage),
            cwd=root,
        )


if __name__ == "__main__":
    main()
