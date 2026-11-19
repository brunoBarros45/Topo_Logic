"""SQLite WAL-mode repository implementations for projects, geometries, and jobs."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from topo_logic.domain.geometry import (
    BoundingBox3D,
    ElementType,
    GeometryAsset,
    GeometryFormat,
    MeshDiagnostics,
    RepairReport,
    VolumeMeshSummary,
)
from topo_logic.domain.jobs import JobRecord, JobStatus, ProjectRecord
from topo_logic.domain.study import StudyType
from topo_logic.domain.units import AxisConvention, ScaleGuardWarning, UnitSystem


class SqliteDatabase:
    """Thread-safe SQLite connection manager initialized with WAL mode and schema."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS geometries (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    format TEXT NOT NULL,
                    unit_system TEXT NOT NULL,
                    axis_convention TEXT NOT NULL,
                    raw_artifact_key TEXT NOT NULL,
                    repaired_artifact_key TEXT,
                    diagnostics_json TEXT NOT NULL,
                    repair_report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_geometries_project_id ON geometries(project_id);

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    study_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    message TEXT NOT NULL,
                    error_message TEXT,
                    result_artifact_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);

                CREATE TABLE IF NOT EXISTS meshes (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    geometry_id TEXT NOT NULL REFERENCES geometries(id) ON DELETE CASCADE,
                    element_type TEXT NOT NULL,
                    node_count INTEGER NOT NULL,
                    element_count INTEGER NOT NULL,
                    total_volume REAL NOT NULL,
                    min_scaled_jacobian REAL NOT NULL,
                    surface_triangle_count INTEGER NOT NULL,
                    artifact_key TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_meshes_project_id ON meshes(project_id);
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class SqliteProjectRepository:
    """SQLite implementation of ProjectRepositoryPort."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    def save(self, project: ProjectRecord) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, description, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description
                """,
                (project.id, project.name, project.description, project.created_at.isoformat()),
            )

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT id, name, description, created_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._row_to_project(row) if row is not None else None

    def list_all(self) -> list[ProjectRecord]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, name, description, created_at FROM projects ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_project(row) for row in rows]

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            id=str(row["id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )


class SqliteGeometryRepository:
    """SQLite implementation of GeometryRepositoryPort."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    def save(self, asset: GeometryAsset) -> None:
        diag_json = json.dumps(self._serialize_diagnostics(asset.diagnostics))
        repair_json = json.dumps(self._serialize_repair_report(asset.repair_report))
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO geometries (
                    id, project_id, filename, format, unit_system, axis_convention,
                    raw_artifact_key, repaired_artifact_key,
                    diagnostics_json, repair_report_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    repaired_artifact_key = excluded.repaired_artifact_key,
                    diagnostics_json = excluded.diagnostics_json,
                    repair_report_json = excluded.repair_report_json
                """,
                (
                    asset.id,
                    asset.project_id,
                    asset.filename,
                    asset.format.value,
                    asset.unit_system.value,
                    asset.axis_convention.value,
                    asset.raw_artifact_key,
                    asset.repaired_artifact_key,
                    diag_json,
                    repair_json,
                    asset.created_at.isoformat(),
                ),
            )

    def get(self, geometry_id: str) -> GeometryAsset | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM geometries WHERE id = ?",
                (geometry_id,),
            ).fetchone()
        return self._row_to_asset(row) if row is not None else None

    def list_by_project(self, project_id: str) -> list[GeometryAsset]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM geometries WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [self._row_to_asset(row) for row in rows]

    @staticmethod
    def _serialize_diagnostics(diag: MeshDiagnostics) -> dict[str, Any]:
        return {
            "vertex_count": diag.vertex_count,
            "triangle_count": diag.triangle_count,
            "connected_components": diag.connected_components,
            "is_watertight": diag.is_watertight,
            "boundary_edge_count": diag.boundary_edge_count,
            "non_manifold_edge_count": diag.non_manifold_edge_count,
            "volume": diag.volume,
            "surface_area": diag.surface_area,
            "bounds": {
                "min_corner": list(diag.bounds.min_corner),
                "max_corner": list(diag.bounds.max_corner),
            },
            "scale_guard": {
                "is_suspicious": diag.scale_guard.is_suspicious,
                "suggested_scale_factor": diag.scale_guard.suggested_scale_factor,
                "suggested_unit_system": (
                    diag.scale_guard.suggested_unit_system.value
                    if diag.scale_guard.suggested_unit_system is not None
                    else None
                ),
                "message": diag.scale_guard.message,
            },
            "warnings": list(diag.warnings),
        }

    @staticmethod
    def _serialize_repair_report(report: RepairReport) -> dict[str, Any]:
        return {
            "applied": report.applied,
            "merged_vertices_count": report.merged_vertices_count,
            "removed_degenerate_faces": report.removed_degenerate_faces,
            "removed_duplicate_faces": report.removed_duplicate_faces,
            "filled_holes": report.filled_holes,
            "normals_fixed": report.normals_fixed,
            "warnings": list(report.warnings),
        }

    @staticmethod
    def _row_to_asset(row: sqlite3.Row) -> GeometryAsset:
        diag_raw: dict[str, Any] = json.loads(str(row["diagnostics_json"]))
        repair_raw: dict[str, Any] = json.loads(str(row["repair_report_json"]))

        bounds_raw = diag_raw["bounds"]
        min_c = bounds_raw["min_corner"]
        max_c = bounds_raw["max_corner"]
        bounds = BoundingBox3D(
            min_corner=(float(min_c[0]), float(min_c[1]), float(min_c[2])),
            max_corner=(float(max_c[0]), float(max_c[1]), float(max_c[2])),
        )

        sg_raw = diag_raw["scale_guard"]
        suggested_unit = sg_raw["suggested_unit_system"]
        scale_guard = ScaleGuardWarning(
            is_suspicious=bool(sg_raw["is_suspicious"]),
            suggested_scale_factor=(
                float(sg_raw["suggested_scale_factor"])
                if sg_raw["suggested_scale_factor"] is not None
                else None
            ),
            suggested_unit_system=(
                UnitSystem(str(suggested_unit)) if suggested_unit is not None else None
            ),
            message=str(sg_raw["message"]) if sg_raw["message"] is not None else None,
        )

        diagnostics = MeshDiagnostics(
            vertex_count=int(diag_raw["vertex_count"]),
            triangle_count=int(diag_raw["triangle_count"]),
            connected_components=int(diag_raw["connected_components"]),
            is_watertight=bool(diag_raw["is_watertight"]),
            boundary_edge_count=int(diag_raw["boundary_edge_count"]),
            non_manifold_edge_count=int(diag_raw["non_manifold_edge_count"]),
            volume=float(diag_raw["volume"]),
            surface_area=float(diag_raw["surface_area"]),
            bounds=bounds,
            scale_guard=scale_guard,
            warnings=tuple(str(w) for w in diag_raw["warnings"]),
        )
        repair_report = RepairReport(
            applied=bool(repair_raw["applied"]),
            merged_vertices_count=int(repair_raw["merged_vertices_count"]),
            removed_degenerate_faces=int(repair_raw["removed_degenerate_faces"]),
            removed_duplicate_faces=int(repair_raw["removed_duplicate_faces"]),
            filled_holes=bool(repair_raw["filled_holes"]),
            normals_fixed=bool(repair_raw["normals_fixed"]),
            warnings=tuple(str(w) for w in repair_raw["warnings"]),
        )

        repaired_key = row["repaired_artifact_key"]
        return GeometryAsset(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            filename=str(row["filename"]),
            format=GeometryFormat(str(row["format"])),
            unit_system=UnitSystem(str(row["unit_system"])),
            axis_convention=AxisConvention(str(row["axis_convention"])),
            raw_artifact_key=str(row["raw_artifact_key"]),
            repaired_artifact_key=str(repaired_key) if repaired_key is not None else None,
            diagnostics=diagnostics,
            repair_report=repair_report,
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )


class SqliteJobRepository:
    """SQLite implementation of JobRepositoryPort."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    def save(self, job: JobRecord) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, project_id, study_type, status, progress, message,
                    error_message, result_artifact_key, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    progress = excluded.progress,
                    message = excluded.message,
                    error_message = excluded.error_message,
                    result_artifact_key = excluded.result_artifact_key,
                    updated_at = excluded.updated_at
                """,
                (
                    job.id,
                    job.project_id,
                    job.study_type.value,
                    job.status.value,
                    job.progress,
                    job.message,
                    job.error_message,
                    job.result_artifact_key,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row is not None else None

    def list_by_project(self, project_id: str) -> list[JobRecord]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        err = row["error_message"]
        res = row["result_artifact_key"]
        return JobRecord(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            study_type=StudyType(str(row["study_type"])),
            status=JobStatus(str(row["status"])),
            progress=float(row["progress"]),
            message=str(row["message"]),
            error_message=str(err) if err is not None else None,
            result_artifact_key=str(res) if res is not None else None,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )


class SqliteMeshRepository:
    """SQLite implementation of MeshRepositoryPort."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    def save(self, mesh: VolumeMeshSummary) -> None:
        created_str = mesh.created_at.isoformat() if mesh.created_at is not None else ""
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO meshes (
                    id, project_id, geometry_id, element_type, node_count, element_count,
                    total_volume, min_scaled_jacobian, surface_triangle_count,
                    artifact_key, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    artifact_key = excluded.artifact_key,
                    total_volume = excluded.total_volume,
                    min_scaled_jacobian = excluded.min_scaled_jacobian
                """,
                (
                    mesh.id,
                    mesh.project_id,
                    mesh.geometry_id,
                    mesh.element_type.value,
                    mesh.node_count,
                    mesh.element_count,
                    mesh.total_volume,
                    mesh.min_scaled_jacobian,
                    mesh.surface_triangle_count,
                    mesh.artifact_key,
                    created_str,
                ),
            )

    def get(self, mesh_id: str) -> VolumeMeshSummary | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM meshes WHERE id = ?", (mesh_id,)).fetchone()
        return self._row_to_mesh(row) if row is not None else None

    def list_by_project(self, project_id: str) -> list[VolumeMeshSummary]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM meshes WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        return [self._row_to_mesh(row) for row in rows]

    @staticmethod
    def _row_to_mesh(row: sqlite3.Row) -> VolumeMeshSummary:
        created_raw = str(row["created_at"])
        created_at = datetime.fromisoformat(created_raw) if created_raw else None
        return VolumeMeshSummary(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            geometry_id=str(row["geometry_id"]),
            element_type=ElementType(str(row["element_type"])),
            node_count=int(row["node_count"]),
            element_count=int(row["element_count"]),
            total_volume=float(row["total_volume"]),
            min_scaled_jacobian=float(row["min_scaled_jacobian"]),
            surface_triangle_count=int(row["surface_triangle_count"]),
            artifact_key=str(row["artifact_key"]),
            created_at=created_at,
        )
