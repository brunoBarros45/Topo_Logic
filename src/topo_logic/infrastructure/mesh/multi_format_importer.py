"""Multi-format surface geometry importers (.STL, .OBJ, .PLY, and optional .STEP CLI)."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import trimesh

from topo_logic.application.ports.geometry import GeometryImporterPort, RawSurfacePayload
from topo_logic.domain.exceptions import (
    DomainValidationError,
    InvalidGeometryError,
    UnsupportedFormatError,
)
from topo_logic.domain.geometry import GeometryFormat


class TrimeshSurfaceImporter:
    """MIT importer supporting binary/ASCII .STL, Wavefront .OBJ, and .PLY surface meshes."""

    _SUPPORTED: frozenset[GeometryFormat] = frozenset(
        {GeometryFormat.STL, GeometryFormat.OBJ, GeometryFormat.PLY}
    )

    def supported_formats(self) -> frozenset[GeometryFormat]:
        return self._SUPPORTED

    def extract_surface_stl(self, payload: RawSurfacePayload) -> bytes:
        if payload.format not in self._SUPPORTED:
            raise UnsupportedFormatError(
                f"Format '.{payload.format.value}' is not supported by TrimeshSurfaceImporter.",
                details={"format": payload.format.value},
            )
        if not payload.raw_bytes:
            raise InvalidGeometryError(f"Uploaded {payload.format.value.upper()} file is empty.")

        try:
            loaded = trimesh.load(
                io.BytesIO(payload.raw_bytes),
                file_type=payload.format.value,
                process=False,
            )
        except Exception as exc:
            raise InvalidGeometryError(
                f"Failed to parse {payload.format.value.upper()} file '{payload.filename}': {exc}",
                details={"filename": payload.filename, "format": payload.format.value},
            ) from exc

        mesh = _coerce_trimesh(loaded, payload.filename)
        if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            raise InvalidGeometryError(
                f"Uploaded file '{payload.filename}' contains zero surface triangles."
            )
        if not bool(np.all(np.isfinite(mesh.vertices))):
            raise InvalidGeometryError(
                f"Uploaded file '{payload.filename}' contains non-finite vertex coordinates."
            )

        if payload.format is GeometryFormat.STL:
            return payload.raw_bytes
        exported = mesh.export(file_type="stl")
        if isinstance(exported, bytes):
            return exported
        if isinstance(exported, str):
            return exported.encode("utf-8")
        raise InvalidGeometryError(
            f"Unexpected STL export payload type from '{payload.filename}'."
        )


class GmshStepImporter:
    """Invokes an external Gmsh CLI binary to tessellate .STEP/.STP CAD models to binary STL."""

    _SUPPORTED: frozenset[GeometryFormat] = frozenset({GeometryFormat.STEP})

    def __init__(self, gmsh_executable: str = "gmsh") -> None:
        self._executable = gmsh_executable

    def supported_formats(self) -> frozenset[GeometryFormat]:
        return self._SUPPORTED

    def extract_surface_stl(self, payload: RawSurfacePayload) -> bytes:
        if payload.format is not GeometryFormat.STEP:
            raise UnsupportedFormatError(
                f"GmshStepImporter supports STEP files, got '.{payload.format.value}'."
            )
        if not payload.raw_bytes:
            raise InvalidGeometryError("Uploaded STEP file is empty.")

        exe_path = shutil.which(self._executable)
        if exe_path is None:
            raise DomainValidationError(
                "Gmsh CLI binary was not found on PATH. Install Gmsh CLI to import .STEP/.STP "
                "CAD models, or export to .STL, .OBJ, or .PLY.",
                details={"executable": self._executable, "format": "step"},
            )

        with tempfile.TemporaryDirectory(prefix="topologic_step_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            step_path = tmp_dir / "model.step"
            geo_path = tmp_dir / "tessellate.geo"
            stl_path = tmp_dir / "surface.stl"

            step_path.write_bytes(payload.raw_bytes)
            geo_script = "\n".join(
                [
                    "SetFactory(\"OpenCASCADE\");",
                    f'Merge "{step_path.as_posix()}";',
                    "Mesh.MeshSizeFromCurvature = 12;",
                    "Mesh.MinimumCurveNodes = 6;",
                    "Mesh 2;",
                    f'Save "{stl_path.as_posix()}";',
                ]
            )
            geo_path.write_text(geo_script, encoding="utf-8")

            proc = subprocess.run(
                [exe_path, str(geo_path), "-2", "-format", "stl", "-o", str(stl_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0 or not stl_path.is_file():
                raise InvalidGeometryError(
                    f"Gmsh CLI STEP tessellation failed (exit {proc.returncode}): "
                    f"{proc.stderr.strip()}"
                )

            stl_bytes = stl_path.read_bytes()

        if not stl_bytes:
            raise InvalidGeometryError("Gmsh STEP tessellation produced an empty STL file.")
        return stl_bytes


class CompositeGeometryImporter:
    """Composite strategy delegating surface ingestion across specialized format importers."""

    def __init__(self, importers: Sequence[GeometryImporterPort]) -> None:
        self._by_format: dict[GeometryFormat, GeometryImporterPort] = {}
        for importer in importers:
            for fmt in importer.supported_formats():
                self._by_format[fmt] = importer

    def supported_formats(self) -> frozenset[GeometryFormat]:
        return frozenset(self._by_format.keys())

    def extract_surface_stl(self, payload: RawSurfacePayload) -> bytes:
        importer = self._by_format.get(payload.format)
        if importer is None:
            supported = sorted(fmt.value for fmt in self._by_format)
            raise UnsupportedFormatError(
                f"Format '.{payload.format.value}' is not enabled. "
                f"Currently supported formats: {supported}.",
                details={"format": payload.format.value, "supported_formats": supported},
            )
        return importer.extract_surface_stl(payload)


def _coerce_trimesh(loaded: object, filename: str) -> trimesh.Trimesh:
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom
            for geom in loaded.dump()
            if isinstance(geom, trimesh.Trimesh) and len(geom.faces) > 0
        ]
        if not meshes:
            raise InvalidGeometryError(
                f"Uploaded scene '{filename}' contains no triangle meshes."
            )
        if len(meshes) == 1:
            return meshes[0]
        combined = trimesh.util.concatenate(meshes)
        if not isinstance(combined, trimesh.Trimesh):
            raise InvalidGeometryError(
                f"Concatenated scene '{filename}' did not produce a valid triangle mesh."
            )
        return combined
    raise InvalidGeometryError(
        f"Uploaded file '{filename}' did not produce a valid triangle mesh."
    )
