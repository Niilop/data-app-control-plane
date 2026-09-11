"""Deterministic template rendering and safe archive creation.

Generation reads reviewed template assets from disk and never fetches anything:
the same template content and the same parameters always produce byte-identical
archives, and therefore the same SHA-256 digest. Archives are stored uncompressed
so the bytes do not depend on the zlib version of the machine that generated them.
"""

import io
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"
ARCHIVE_MEDIA_TYPE = "application/zip"
REPORT_MEDIA_TYPE = "application/json"

PLACEHOLDER = re.compile(r"@@([a-z][a-z0-9_]*)@@")
SEGMENT = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_ENTRIES = 100
MAX_ENTRY_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 8_000_000
MAX_PATH_LENGTH = 200
# 1980-01-01 is the earliest timestamp the ZIP format can represent.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = 0o100644 << 16
ZIP_UNIX = 3


class GenerationError(Exception):
    """A template asset or parameter set that cannot produce a safe archive."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class TemplateFile:
    source: str
    target: str


@dataclass(frozen=True)
class Template:
    """One immutable on-disk template version, identified by its content digest."""

    name: str
    version: str
    title: str
    summary: str
    active: bool
    payload_version: int
    tool_versions: dict
    supplied_parameters: list[dict]
    derived_parameters: list[dict]
    required_targets: tuple[str, ...]
    files: tuple[TemplateFile, ...]
    content_digest: str
    root: Path

    @property
    def reference(self) -> str:
        return f"{self.name}@{self.version}"


def safe_archive_path(value: str) -> str:
    """Reject absolute, traversing, hidden-encoding or otherwise unsafe entries."""
    if not value or len(value) > MAX_PATH_LENGTH or value != value.strip():
        raise GenerationError("unsafe_archive_entry", "Invalid archive entry path")
    if value.startswith("/") or "\\" in value or ":" in value:
        raise GenerationError("unsafe_archive_entry", "Invalid archive entry path")
    segments = value.split("/")
    for segment in segments:
        if segment in {"", ".", ".."} or not SEGMENT.fullmatch(segment):
            raise GenerationError("unsafe_archive_entry", "Invalid archive entry path")
    if len(segments) > 10:
        raise GenerationError("unsafe_archive_entry", "Archive entry is too deep")
    return value


def render(text: str, values: Mapping[str, str]) -> str:
    """Substitute @@name@@ placeholders; an unknown name is a template defect."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise GenerationError(
                "unknown_template_parameter",
                f"Template refers to an unknown parameter: {name}",
            )
        return values[name]

    return PLACEHOLDER.sub(replace, text)


def read_asset(path: Path) -> str:
    """Read a template asset as strict UTF-8 with normalized line endings."""
    try:
        data = path.read_bytes()
    except OSError:
        raise GenerationError(
            "template_asset_missing", "Template asset is unavailable"
        ) from None
    if b"\r" in data or b"\x00" in data:
        raise GenerationError(
            "template_asset_invalid", "Template assets must use LF text encoding"
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise GenerationError(
            "template_asset_invalid", "Template assets must be UTF-8"
        ) from None


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def canonical_digest(value: object) -> str:
    return digest_bytes(canonical_json(value))


def _content_digest(manifest: bytes, sources: list[tuple[str, str]]) -> str:
    """Digest the manifest plus every asset, so any edit changes the identity."""
    hasher = sha256()
    hasher.update(b"template-manifest\0" + sha256(manifest).digest())
    for source, text in sorted(sources):
        hasher.update(b"template-file\0" + source.encode() + b"\0")
        hasher.update(sha256(text.encode()).digest())
    return hasher.hexdigest()


def _load_template(directory: Path) -> Template:
    manifest_path = directory / "template.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    files = tuple(
        TemplateFile(source=item["source"], target=item["target"])
        for item in manifest["files"]
    )
    if not files or len(files) > MAX_ENTRIES:
        raise GenerationError("template_asset_invalid", "Unsupported template size")
    sources = []
    for item in files:
        safe_archive_path(item.source)
        sources.append((item.source, read_asset(directory / "files" / item.source)))
    return Template(
        name=manifest["name"],
        version=manifest["version"],
        title=manifest["title"],
        summary=manifest["summary"],
        active=bool(manifest["active"]),
        payload_version=int(manifest["payload_version"]),
        tool_versions=manifest["tool_versions"],
        supplied_parameters=manifest["supplied_parameters"],
        derived_parameters=manifest["derived_parameters"],
        required_targets=tuple(manifest["required_targets"]),
        files=files,
        content_digest=_content_digest(manifest_bytes, sources),
        root=directory,
    )


@lru_cache(maxsize=1)
def load_catalogue() -> tuple[Template, ...]:
    """Read every reviewed template version shipped with this process."""
    directories = sorted(
        path.parent
        for path in TEMPLATE_ROOT.glob("*/*/template.json")
        if path.is_file()
    )
    return tuple(_load_template(directory) for directory in directories)


def get_template(name: str, version: str) -> Template:
    for template in load_catalogue():
        if template.name == name and template.version == version:
            if not template.active:
                raise GenerationError(
                    "template_inactive", "Template version is not approved for use"
                )
            return template
    raise GenerationError("unknown_template", "Template version is not available")


def build_archive(template: Template, values: Mapping[str, str]) -> bytes:
    """Render every allowed file into one deterministic, uncompressed archive."""
    entries: dict[str, bytes] = {}
    for item in template.files:
        target = safe_archive_path(render(item.target, values))
        if target in entries:
            raise GenerationError(
                "unsafe_archive_entry", "Duplicate archive entry path"
            )
        data = render(
            read_asset(template.root / "files" / item.source), values
        ).encode()
        if len(data) > MAX_ENTRY_BYTES:
            raise GenerationError("unsafe_archive_entry", "Archive entry is too large")
        entries[target] = data
    missing = [target for target in template.required_targets if target not in entries]
    if missing:
        raise GenerationError(
            "incomplete_template", "Template does not produce its required files"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        # Sorted entries, a fixed timestamp, fixed permissions and no compression
        # keep the bytes identical across machines, runs and Python builds.
        for target, data in sorted(entries.items()):
            info = zipfile.ZipInfo(target, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = ZIP_UNIX
            info.external_attr = ZIP_MODE
            archive.writestr(info, data)
    content = buffer.getvalue()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise GenerationError("unsafe_archive_entry", "Archive is too large")
    return content


def read_archive(content: bytes) -> dict[str, bytes]:
    """Read a stored archive, rejecting any entry that is unsafe to extract."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ENTRIES:
                raise GenerationError(
                    "unsafe_archive_entry", "Unsupported archive entry count"
                )
            entries: dict[str, bytes] = {}
            for info in infos:
                if info.is_dir():
                    raise GenerationError(
                        "unsafe_archive_entry", "Directory entries are not allowed"
                    )
                mode = (info.external_attr >> 16) & 0o170000
                if mode not in (0, 0o100000):
                    raise GenerationError(
                        "unsafe_archive_entry", "Only regular files are allowed"
                    )
                target = safe_archive_path(info.filename)
                if target in entries or info.file_size > MAX_ENTRY_BYTES:
                    raise GenerationError(
                        "unsafe_archive_entry", "Invalid archive entry"
                    )
                entries[target] = archive.read(info)
            return entries
    except (zipfile.BadZipFile, OSError):
        raise GenerationError(
            "unreadable_archive", "Archive could not be read"
        ) from None
