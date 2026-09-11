"""Content-addressed local artifact storage with verification on every read.

The store lives in a configured directory that the API and worker both mount, so
artifacts outlive either process. It is not a private filesystem of one process;
moving to another host requires migrating this directory (see architecture.md).
"""

import os
import tempfile
from pathlib import Path

from core.config import Settings, get_settings
from services.policy_service import PolicyError
from services.template_service import digest_bytes

DIGEST_LENGTH = 64
MAX_ARTIFACT_BYTES = 8_000_000


def artifact_root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return Path(settings.artifact_dir)


def valid_digest(digest: str) -> str:
    if len(digest) != DIGEST_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise PolicyError(422, "invalid_digest", "Supply a lowercase SHA-256 digest")
    return digest


def storage_key(digest: str) -> str:
    """Fan out by digest prefix; the key never encodes an application or actor."""
    valid_digest(digest)
    return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def _path(digest: str, settings: Settings | None = None) -> Path:
    return artifact_root(settings) / storage_key(digest)


def put(content: bytes, settings: Settings | None = None) -> tuple[str, int]:
    """Store content under its own digest and return that digest and its size.

    Writing is atomic: a partially written file is never visible under its final
    key. Identical content is stored once; existing content is left untouched
    because artifact content is immutable.
    """
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise PolicyError(422, "invalid_artifact", "Unsupported artifact size")
    digest = digest_bytes(content)
    destination = _path(digest, settings)
    if destination.exists():
        return digest, len(content)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".partial")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return digest, len(content)


def get(digest: str, settings: Settings | None = None) -> bytes:
    """Return stored content only when it still hashes to the requested digest."""
    valid_digest(digest)
    path = _path(digest, settings)
    try:
        content = path.read_bytes()
    except OSError:
        raise PolicyError(
            404, "artifact_unavailable", "Artifact content is not in this store"
        ) from None
    if digest_bytes(content) != digest:
        # Never serve content that does not match its recorded identity.
        raise PolicyError(
            500, "artifact_digest_mismatch", "Stored artifact failed verification"
        )
    return content


def exists(digest: str, settings: Settings | None = None) -> bool:
    valid_digest(digest)
    return _path(digest, settings).is_file()
