"""Local filesystem implementation of ArtifactStoragePort with path-traversal protection."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from topo_logic.domain.exceptions import DomainValidationError, ResourceNotFoundError


class LocalFsArtifactStorage:
    """Persists raw and processed binary artifacts safely under a local root directory."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir.resolve()
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, key: str, data: bytes) -> str:
        target = self._resolve_safe(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp_", suffix=".bin")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp_name, target)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        return self._normalize_key(key)

    def read_bytes(self, key: str) -> bytes:
        target = self._resolve_safe(key)
        if not target.is_file():
            raise ResourceNotFoundError(
                f"Artifact '{key}' was not found.",
                details={"artifact_key": key},
            )
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve_safe(key).is_file()

    def delete(self, key: str) -> None:
        target = self._resolve_safe(key)
        if target.is_file():
            target.unlink()

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.replace("\\", "/").strip("/")

    def _resolve_safe(self, key: str) -> Path:
        raw = key.strip()
        if not raw or raw.startswith(("/", "\\")) or Path(raw).is_absolute():
            raise DomainValidationError(
                "Artifact key must be a non-empty relative path.",
                details={"artifact_key": key},
            )

        normalized = self._normalize_key(raw)
        if not normalized:
            raise DomainValidationError("Artifact key must not be empty.")

        candidate_rel = Path(normalized)
        if candidate_rel.is_absolute():
            raise DomainValidationError(
                "Artifact key must be relative.",
                details={"artifact_key": key},
            )

        resolved = (self._root_dir / candidate_rel).resolve()
        if not resolved.is_relative_to(self._root_dir):
            raise DomainValidationError(
                "Artifact key escapes the storage root directory.",
                details={"artifact_key": key},
            )
        return resolved
