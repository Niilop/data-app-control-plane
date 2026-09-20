"""Install/test only the approved generated template in a disposable offline project."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from models.delivery_schemas import TemplateParameters  # noqa: E402
from services.template_service import render, unpack  # noqa: E402


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required")
    content = render("synthetic-check", "dev", {}, TemplateParameters())
    with TemporaryDirectory(prefix="generated-project-check-") as temporary:
        root = Path(temporary)
        project = root / "project"
        project.mkdir()
        for name, data in unpack(content).items():
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        environment = {
            "PATH": os.environ["PATH"],
            "UV_CACHE_DIR": str(root / "cache"),
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_PYTHON": sys.executable,
            "UV_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # A fresh cache proves this dependency-free lock needs no downloaded packages.
        for arguments in (
            ["sync", "--locked", "--offline"],
            [
                "run",
                "--locked",
                "--offline",
                "python",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
        ):
            subprocess.run(
                [uv, *arguments], cwd=project, env=environment, check=True, timeout=60
            )
    print("Generated project: locked offline installation and tests passed")


if __name__ == "__main__":
    main()
