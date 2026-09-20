"""Bounded content-addressed local storage. Atomic publication, no path inputs."""

import os
import re
import stat
import tempfile
from pathlib import Path

from services.template_service import MAX_BYTES, sha


class ArtifactError(Exception):
    """Sanitized storage failure."""


class LocalArtifacts:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, digest: str) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ArtifactError("Invalid digest")
        try:
            descriptor = os.open(
                self.root / digest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
            with os.fdopen(descriptor, "rb") as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
                    raise ArtifactError("Invalid artifact")
                data = source.read(MAX_BYTES + 1)
            if sha(data) != digest or len(data) > MAX_BYTES:
                raise ArtifactError("Artifact integrity check failed")
            return data
        except OSError:
            raise ArtifactError("Artifact unavailable") from None

    def put(self, data: bytes) -> str:
        if len(data) > MAX_BYTES:
            raise ArtifactError("Artifact exceeds limits")
        digest = sha(data)
        temporary = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self.root, prefix=".pending-", delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, self.root / digest)
            except FileExistsError:
                pass
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.read(digest)
            return digest
        except OSError:
            raise ArtifactError("Artifact unavailable") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
