"""Versioned, closed-input template rendering and canonical safe ZIP archives."""

import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

from models.delivery_schemas import TemplateParameters

ASSETS = Path(__file__).resolve().parents[1] / "templates" / "python_batch_v1"
TEMPLATE_ID = "python-batch:1.0.0"
MAX_BYTES = 2_000_000


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or len(name) > 200
        or path.is_absolute()
        or any(p in {"", ".", ".."} for p in name.split("/"))
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
    ):
        raise ValueError("Unsafe archive path")


def archive(files: dict[str, bytes]) -> bytes:
    if len(files) > 50 or sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("Archive exceeds limits")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as output:
        for name, data in sorted(files.items()):
            safe_path(name)
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            output.writestr(entry, data)
    return buffer.getvalue()


def unpack(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_BYTES:
        raise ValueError("Archive exceeds limits")
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        entries = source.infolist()
        if len(entries) > 50 or sum(e.file_size for e in entries) > MAX_BYTES:
            raise ValueError("Archive exceeds limits")
        files = {}
        for entry in entries:
            safe_path(entry.filename)
            if (
                entry.filename in files
                or entry.is_dir()
                or entry.flag_bits & 1
                or entry.compress_type != zipfile.ZIP_STORED
                or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG
            ):
                raise ValueError("Unsafe archive entry")
            files[entry.filename] = source.read(entry)
        return files


def template_files() -> dict[str, bytes]:
    return {
        p.relative_to(ASSETS).as_posix(): p.read_bytes()
        for p in sorted(ASSETS.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def template_digest() -> str:
    return sha(archive(template_files()))


def render(
    slug: str, target: str, config: dict, parameters: TemplateParameters
) -> bytes:
    # Validate even when called by a worker or directly, not only through HTTP.
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", slug):
        raise ValueError("Invalid application slug")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", target):
        raise ValueError("Invalid target")
    from models.environment_schemas import SafeBindingConfig

    config = SafeBindingConfig.model_validate(config).model_dump()
    parameters = TemplateParameters.model_validate(parameters.model_dump())
    replacements = {
        "__SLUG__": slug,
        "__TARGET__": target,
        "__PACKAGE__": parameters.package_name,
        "__ROWS__": str(config["synthetic_row_count"]),
        "__TIMEOUT__": str(config["max_runtime_seconds"]),
    }
    files = {}
    for path, content in template_files().items():
        value = content.decode()
        for old, new in replacements.items():
            path, value = path.replace(old, new), value.replace(old, new)
        files[path] = value.encode()
    files["manifest.json"] = canonical(
        {
            "schema_version": 1,
            "template_id": TEMPLATE_ID,
            "template_digest": template_digest(),
            "slug": slug,
            "target": target,
            "parameters": parameters.model_dump(),
            "config": config,
            "config_digest": sha(canonical(config)),
            "parameters_digest": sha(canonical(parameters.model_dump())),
            "tools": {"uv": "0.12.11", "python": ">=3.11", "validator": "static-v1"},
            "files": {name: sha(value) for name, value in sorted(files.items())},
        }
    )
    return archive(files)
