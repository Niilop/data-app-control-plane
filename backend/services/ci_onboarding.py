"""Generate a reviewed overlay without changing immutable template assets."""

from pathlib import Path

from models.platform_schemas import validate_bundle_root
from services.template_service import archive

ASSETS = Path(__file__).resolve().parents[1] / "templates" / "github_ci_v1"


def render(bundle_root: str) -> bytes:
    validate_bundle_root(bundle_root)
    mapping = {
        "workflow.yml": ".github/workflows/batch-ci.yml",
        "README.md": "CI-ONBOARDING.md",
        "pyproject.toml": ".control-plane-ci/pyproject.toml",
        "uv.lock": ".control-plane-ci/uv.lock",
        "check.py": ".control-plane-ci/check.py",
    }
    return archive(
        {
            target: (ASSETS / name)
            .read_text()
            .replace("__BUNDLE_ROOT__", bundle_root)
            .encode()
            for name, target in mapping.items()
        }
    )
