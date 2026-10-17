"""Exercise the generated CI overlay locally using only our approved template."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from models.delivery_schemas import TemplateParameters  # noqa: E402
from services.ci_onboarding import render as onboarding  # noqa: E402
from services.template_service import render, unpack  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="ci-onboarding-check-") as temporary:
        root = Path(temporary)
        for content, prefix in (
            (render("ci-check", "dev", {}, TemplateParameters()), "bundles/batch/"),
            (onboarding("bundles/batch"), ""),
        ):
            for name, data in unpack(content).items():
                target = root / (prefix + name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        environment = {
            **os.environ,
            "BUNDLE_ROOT": "bundles/batch",
            "UV_PYTHON": sys.executable,
        }
        environment.pop("VIRTUAL_ENV", None)
        # Exercise the documented, reviewed v1 import-order migration. The original
        # renderer stays immutable; the workflow must fail on uncorrected lint.
        test_file = root / "bundles/batch/tests/test_batch.py"
        before = test_file.read_text()
        subprocess.run(
            [
                "uv",
                "run",
                "--locked",
                "--project",
                ".control-plane-ci",
                "ruff",
                "check",
                "--isolated",
                "--fix",
                "bundles/batch/src",
                "bundles/batch/tests",
            ],
            cwd=root,
            env=environment,
            check=True,
            timeout=180,
        )
        assert test_file.read_text() == before.replace(
            "import unittest\n", "import unittest\n\n", 1
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--locked",
                "--project",
                ".control-plane-ci",
                "python",
                ".control-plane-ci/check.py",
            ],
            cwd=root,
            env=environment,
            check=True,
            timeout=180,
        )
    print(
        "Generated CI overlay: locked tools, lint, types, unit tests, static checks and wheel build passed"
    )


if __name__ == "__main__":
    main()
