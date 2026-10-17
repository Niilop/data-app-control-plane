"""Bounded in-memory inspection of GitHub ZIPs; repository code is never executed."""

import ast
import io
import json
import stat
import tomllib
import zipfile

from integrations.github import GitHubError
from models.delivery_schemas import TemplateParameters
from services.template_service import (
    MAX_BYTES,
    TEMPLATE_ID,
    archive,
    safe_path,
    template_digest,
)


def inspect_bundle(files: dict[str, bytes], binding: dict) -> None:
    """Check the approved Python batch structure, not workspace deployability."""
    required = {"manifest.json", "databricks.yml", "pyproject.toml", "uv.lock"}
    if not required.issubset(files):
        raise ValueError("Missing bundle files")
    manifest = json.loads(files["manifest.json"])
    if not isinstance(manifest, dict) or (
        manifest.get("schema_version") != 1
        or manifest.get("template_id") != TEMPLATE_ID
        or manifest.get("template_digest") != template_digest()
        or manifest.get("target") != binding["bundle_target"]
        or manifest.get("config") != binding["config"]
    ):
        raise ValueError("Incompatible bundle manifest")
    parameters = TemplateParameters.model_validate(manifest.get("parameters"))
    if f"src/{parameters.package_name}/batch.py" not in files or not any(
        name.startswith("tests/") and name.endswith(".py") for name in files
    ):
        raise ValueError("Missing Python batch structure")
    for name, content in files.items():
        if name.endswith(".py"):
            ast.parse(content)
        elif name.endswith(".toml") or name == "uv.lock":
            tomllib.loads(content.decode())
    # Bundle YAML is preserved as data. Databricks semantic validation is a later gate.
    files["databricks.yml"].decode("utf-8")


def capture_archive(data: bytes, bundle_root: str, binding: dict) -> bytes:
    try:
        if len(data) > MAX_BYTES:
            raise ValueError("Archive too large")
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            entries = source.infolist()
            if len(entries) > 500 or sum(e.file_size for e in entries) > MAX_BYTES:
                raise ValueError("Archive too large")
            files: dict[str, bytes] = {}
            seen: set[str] = set()
            root: str | None = None
            for entry in entries:
                name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
                safe_path(name)
                prefix, _, relative = name.partition("/")
                root = root or prefix
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (
                    prefix != root
                    or name in seen
                    or entry.flag_bits & 1
                    or entry.compress_type
                    not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or mode not in {0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG}
                    or (not relative and not entry.is_dir())
                ):
                    raise ValueError("Unsafe archive entry")
                seen.add(name)
                if entry.is_dir():
                    continue
                if bundle_root != ".":
                    if not relative.startswith(bundle_root + "/"):
                        continue
                    relative = relative[len(bundle_root) + 1 :]
                # Never retain credentials, even inside an otherwise valid bundle.
                if any(
                    p in {".git", ".env", ".aws", ".ssh"} for p in relative.split("/")
                ):
                    raise ValueError("Forbidden bundle file")
                files[relative] = source.read(entry)
            inspect_bundle(files, binding)
            result = archive(files)
            if len(result) > MAX_BYTES:
                raise ValueError("Archive too large")
            return result
    except (
        ValueError,
        KeyError,
        TypeError,
        SyntaxError,
        UnicodeError,
        zipfile.BadZipFile,
        NotImplementedError,
        RuntimeError,
    ):
        raise GitHubError("github_invalid_bundle") from None
