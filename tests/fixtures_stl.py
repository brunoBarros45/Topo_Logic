"""Programmatic STL fixture generators for unit and integration tests."""

from __future__ import annotations

import trimesh


def make_cube_stl_bytes(size: float = 20.0, *, binary: bool = True) -> bytes:
    """Create a watertight cube STL centered at the origin."""
    box = trimesh.creation.box(extents=(size, size, size))
    file_type = "stl" if binary else "stl_ascii"
    exported = box.export(file_type=file_type)
    if isinstance(exported, bytes):
        return exported
    return str(exported).encode("ascii")


def make_inverted_cube_stl_bytes(size: float = 20.0) -> bytes:
    """Create a cube STL with inverted winding (negative enclosed volume)."""
    box = trimesh.creation.box(extents=(size, size, size))
    box.invert()
    exported = box.export(file_type="stl")
    return exported if isinstance(exported, bytes) else bytes(exported)


def make_single_triangle_hole_stl_bytes(size: float = 20.0) -> bytes:
    """Create a cube STL missing one triangle (repairable by Tier-1 fill_holes)."""
    box = trimesh.creation.box(extents=(size, size, size))
    keep_mask = [i != 0 for i in range(len(box.faces))]
    box.update_faces(keep_mask)
    exported = box.export(file_type="stl")
    return exported if isinstance(exported, bytes) else bytes(exported)
