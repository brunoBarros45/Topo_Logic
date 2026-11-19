"""FastAPI router registrations."""

from __future__ import annotations

from topo_logic.interfaces.api.routers import (
    geometries,
    health,
    jobs,
    materials,
    meshes,
    projects,
    studies,
)

__all__ = ["geometries", "health", "jobs", "materials", "meshes", "projects", "studies"]
