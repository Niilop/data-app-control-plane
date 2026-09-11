"""Generate a bundle and verify the extracted project in an isolated directory.

This is the T05 acceptance check that a generated project installs from its own
lock file and passes its own tests. It uses only the local template assets: uv
runs with `--offline`, so a missing lock entry or an accidentally introduced
third-party dependency fails here rather than silently reaching out to an index.

    uv run --locked python scripts/check_generated_project.py

Nothing is published, deployed or sent anywhere. The temporary project directory
is removed afterwards.
"""

import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.template_service import (  # noqa: E402
    build_archive,
    get_template,
    read_archive,
)

SLUG = "synthetic-sales"
PACKAGE = "synthetic_sales"
VALUES = {
    "application_slug": SLUG,
    "package_name": PACKAGE,
    "package_dist_name": PACKAGE.replace("_", "-"),
    "bundle_target": "sandbox",
    "synthetic_output_path": "output/synthetic.csv",
    "synthetic_row_count": "100",
    "max_runtime_seconds": "300",
    "template_name": "python-batch",
    "template_version": "1.0.0",
}


def run(command: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"Command failed: {' '.join(command)}")
    print((result.stdout or result.stderr).strip()[-2000:] or "(no output)")


def main() -> int:
    if shutil.which("uv") is None:
        raise SystemExit("uv is required; install it before running this check")
    template = get_template(VALUES["template_name"], VALUES["template_version"])
    first = build_archive(template, VALUES)
    second = build_archive(template, VALUES)
    if first != second:
        raise SystemExit("Generation is not deterministic")
    digest = sha256(first).hexdigest()
    print(f"Template {template.reference} content digest {template.content_digest}")
    print(
        f"Archive digest {digest} ({len(first)} bytes, {len(read_archive(first))} files)"
    )

    with tempfile.TemporaryDirectory(prefix="generated-project-") as directory:
        project = Path(directory) / SLUG
        for name, data in sorted(read_archive(first).items()):
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # --offline proves the lock needs no index; --no-managed-python avoids
        # downloading an interpreter on a machine that already has a suitable one.
        run(["uv", "sync", "--locked", "--offline", "--no-managed-python"], project)
        run(
            [
                "uv",
                "run",
                "--offline",
                "--no-managed-python",
                "python",
                "-m",
                "unittest",
                "discover",
                "--start-directory",
                "tests",
                "--top-level-directory",
                ".",
                "--verbose",
            ],
            project,
        )
        run(
            [
                "uv",
                "run",
                "--offline",
                "--no-managed-python",
                "python",
                f"src/{PACKAGE}/main.py",
                "--rows",
                "5",
                "--output",
                "output/check.csv",
            ],
            project,
        )
        rows = (project / "output" / "check.csv").read_text().splitlines()
        if len(rows) != 6:
            raise SystemExit(f"Expected a header and 5 rows, found {len(rows)}")
    print("\nGenerated project installed from its lock and passed its own tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
