"""STL surface geometry importer backed by trimesh (MIT)."""

from __future__ import annotations

import io

import numpy as np
import trimesh

from topo_logic.application.ports.geometry import RawSurfacePayload
from topo_logic.domain.exceptions import InvalidGeometryError, UnsupportedFormatError
from topo_logic.domain.geometry import GeometryFormat


class TrimeshStlImporter:
    """Phase 1 GeometryImporterPort supporting binary and ASCII STL files."""

    _SUPPORTED: frozenset[GeometryFormat] = frozenset({GeometryFormat.STL})

    def supported_formats(self) -> frozenset[GeometryFormat]:
        return self._SUPPORTED

    def extract_surface_stl(self, payload: RawSurfacePayload) -> bytes:
        if payload.format not in self._SUPPORTED:
            raise UnsupportedFormatError(
                f"Format '.{payload.format.value}' is not supported by TrimeshStlImporter.",
                details={"format": payload.format.value},
            )

        if not payload.raw_bytes:
            raise InvalidGeometryError("Uploaded STL file is empty.")

        try:
            loaded = trimesh.load(
                io.BytesIO(payload.raw_bytes),
                file_type="stl",
                force="mesh",
                process=False,
            )
        except Exception as exc:
            raise InvalidGeometryError(
                f"Failed to parse STL file '{payload.filename}': {exc}",
                details={"filename": payload.filename},
            ) from exc

        if not isinstance(loaded, trimesh.Trimesh):
            raise InvalidGeometryError(
                f"Uploaded STL '{payload.filename}' did not produce a valid triangle mesh."
            )

        if len(loaded.vertices) == 0 or len(loaded.faces) == 0:
            raise InvalidGeometryError(
                f"Uploaded STL '{payload.filename}' contains zero triangles."
            )

        if not bool(np.all(np.isfinite(loaded.vertices))):
            raise InvalidGeometryError(
                f"Uploaded STL '{payload.filename}' contains non-finite vertex coordinates."
            )

        return payload.raw_bytes
