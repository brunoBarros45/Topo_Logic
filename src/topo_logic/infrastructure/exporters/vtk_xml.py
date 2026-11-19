"""Binary VTK XML (.vtp, .vti, .vtu) writers with zlib compression (100% MIT)."""

from __future__ import annotations

import io
import struct
import zlib
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from topo_logic.domain.exceptions import DomainValidationError, InvalidGeometryError
from topo_logic.domain.geometry import ElementType
from topo_logic.infrastructure.mesh.volume_mesh import VolumeMeshData

_VTK_TYPE_MAP: dict[str, str] = {
    "float32": "Float32",
    "int32": "Int32",
    "uint8": "UInt8",
}

_VTK_CELL_TYPE_MAP: dict[ElementType, int] = {
    ElementType.H8: 12,     # VTK_HEXAHEDRON
    ElementType.C3D4: 10,   # VTK_TETRA
    ElementType.C3D10: 24,  # VTK_QUADRATIC_TETRA
}


def extract_load_case_fields(
    bundle_bytes: bytes,
    load_case_id: str,
) -> dict[str, NDArray[np.float32]]:
    """Extract all post-processed Float32 arrays for one FEM load case."""
    prefix = f"{load_case_id}__"
    result: dict[str, NDArray[np.float32]] = {}
    with np.load(io.BytesIO(bundle_bytes), allow_pickle=False) as archive:
        for key in archive.files:
            if key.startswith(prefix):
                field_name = key[len(prefix) :]
                result[field_name] = np.ascontiguousarray(archive[key], dtype="<f4")
    if not result:
        raise KeyError(load_case_id)
    return result


def export_mesh_surface_vtp(mesh: VolumeMeshData) -> bytes:
    """Export exterior boundary surface of VolumeMeshData as compressed VTK PolyData (.vtp)."""
    used_nodes, _remap, surf_tris = _compact_surface_triangles(mesh)
    points_f32 = np.ascontiguousarray(mesh.nodes[used_nodes], dtype="<f4")
    connectivity = np.ascontiguousarray(surf_tris.ravel(), dtype="<i4")
    offsets = np.arange(3, 3 * len(surf_tris) + 1, 3, dtype="<i4")

    point_arrays: list[tuple[str, NDArray[np.generic], int]] = [
        ("original_node_id", np.ascontiguousarray(used_nodes, dtype="<i4"), 1),
    ]
    cell_arrays: list[tuple[str, NDArray[np.generic], int]] = []
    if mesh.surface_face_tags is not None and len(mesh.surface_face_tags) == len(surf_tris):
        unique_tags = {tag: idx for idx, tag in enumerate(sorted(set(mesh.surface_face_tags)))}
        tag_ids = np.asarray(
            [unique_tags[tag] for tag in mesh.surface_face_tags],
            dtype="<i4",
        )
        cell_arrays.append(("face_group_id", tag_ids, 1))

    return _build_vtp_bytes(
        points=points_f32,
        connectivity=connectivity,
        offsets=offsets,
        n_verts=len(used_nodes),
        n_polys=len(surf_tris),
        point_arrays=point_arrays,
        cell_arrays=cell_arrays,
    )


def export_fem_surface_vtp(
    mesh: VolumeMeshData,
    fields: dict[str, NDArray[np.float32]],
) -> bytes:
    """Export FEM boundary surface with mapped displacement, Von Mises, and safety factor."""
    used_nodes, _remap, surf_tris = _compact_surface_triangles(mesh)
    points_f32 = np.ascontiguousarray(mesh.nodes[used_nodes], dtype="<f4")
    connectivity = np.ascontiguousarray(surf_tris.ravel(), dtype="<i4")
    offsets = np.arange(3, 3 * len(surf_tris) + 1, 3, dtype="<i4")

    point_arrays: list[tuple[str, NDArray[np.generic], int]] = [
        ("original_node_id", np.ascontiguousarray(used_nodes, dtype="<i4"), 1),
    ]
    for name in ("displacement", "displacement_magnitude", "von_mises", "safety_factor"):
        if name not in fields:
            continue
        arr = np.asarray(fields[name], dtype="<f4")
        sliced = np.ascontiguousarray(arr[used_nodes], dtype="<f4")
        n_comp = sliced.shape[1] if sliced.ndim == 2 else 1
        point_arrays.append((name, sliced, n_comp))

    return _build_vtp_bytes(
        points=points_f32,
        connectivity=connectivity,
        offsets=offsets,
        n_verts=len(used_nodes),
        n_polys=len(surf_tris),
        point_arrays=point_arrays,
        cell_arrays=[],
        default_scalars="von_mises" if "von_mises" in fields else "",
        default_vectors="displacement" if "displacement" in fields else "",
    )


def export_fem_volume_vtu(
    mesh: VolumeMeshData,
    *,
    point_fields: dict[str, NDArray[np.float32]] | None = None,
    cell_fields: dict[str, NDArray[np.float32]] | None = None,
) -> bytes:
    """Export full 3D volumetric mesh (H8/C3D4/C3D10) + fields as VTK UnstructuredGrid (.vtu)."""
    cell_type_id = _VTK_CELL_TYPE_MAP.get(mesh.element_type)
    if cell_type_id is None:
        raise DomainValidationError(
            f"Unsupported element type for .vtu export: '{mesh.element_type.value}'."
        )

    n_pts = len(mesh.nodes)
    n_cells = len(mesh.elements)
    nodes_per_cell = mesh.elements.shape[1]

    points_f32 = np.ascontiguousarray(mesh.nodes, dtype="<f4")
    connectivity = np.ascontiguousarray(mesh.elements.ravel(), dtype="<i4")
    offsets = (np.arange(1, n_cells + 1, dtype="<i4") * nodes_per_cell).astype("<i4")
    cell_types = np.full(n_cells, cell_type_id, dtype="<u1")

    point_arrays: list[tuple[str, NDArray[np.generic], int]] = []
    for name, arr in (point_fields or {}).items():
        data = np.ascontiguousarray(arr, dtype="<f4")
        n_comp = data.shape[1] if data.ndim == 2 else 1
        point_arrays.append((name, data, n_comp))

    cell_arrays: list[tuple[str, NDArray[np.generic], int]] = []
    for name, arr in (cell_fields or {}).items():
        data = np.ascontiguousarray(arr, dtype="<f4")
        n_comp = data.shape[1] if data.ndim == 2 else 1
        cell_arrays.append((name, data, n_comp))

    appended_chunks: list[bytes] = []
    current_offset = 0

    def _register(name: str, arr: NDArray[np.generic], n_comp: int) -> str:
        nonlocal current_offset
        vtk_type = _resolve_vtk_type(arr)
        blob = _encode_vtk_zlib_block(arr)
        tag = (
            f'<DataArray type="{vtk_type}" Name="{escape(name)}" '
            f'NumberOfComponents="{n_comp}" format="appended" offset="{current_offset}"/>'
        )
        appended_chunks.append(blob)
        current_offset += len(blob)
        return tag

    points_tag = _register("Points", points_f32, 3)
    conn_tag = _register("connectivity", connectivity, 1)
    offsets_tag = _register("offsets", offsets, 1)
    types_tag = _register("types", cell_types, 1)

    pd_tags = "\n".join(_register(n, a, c) for n, a, c in point_arrays)
    cd_tags = "\n".join(_register(n, a, c) for n, a, c in cell_arrays)

    pd_attrs = ' Scalars="von_mises"' if point_fields and "von_mises" in point_fields else ""
    if point_fields and "displacement" in point_fields:
        pd_attrs += ' Vectors="displacement"'
    cd_attrs = ' Scalars="density"' if cell_fields and "density" in cell_fields else ""

    header_xml = (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian" '
        'header_type="UInt32" compressor="vtkZLibDataCompressor">\n'
        "  <UnstructuredGrid>\n"
        f'    <Piece NumberOfPoints="{n_pts}" NumberOfCells="{n_cells}">\n'
        f"      <PointData{pd_attrs}>\n"
        f"        {pd_tags}\n"
        "      </PointData>\n"
        f"      <CellData{cd_attrs}>\n"
        f"        {cd_tags}\n"
        "      </CellData>\n"
        "      <Points>\n"
        f"        {points_tag}\n"
        "      </Points>\n"
        "      <Cells>\n"
        f"        {conn_tag}\n"
        f"        {offsets_tag}\n"
        f"        {types_tag}\n"
        "      </Cells>\n"
        "    </Piece>\n"
        "  </UnstructuredGrid>\n"
        '  <AppendedData encoding="raw">\n_'
    ).encode("ascii")

    return header_xml + b"".join(appended_chunks) + b"\n  </AppendedData>\n</VTKFile>\n"


def export_topopt_densities_vti(density_payload: bytes) -> bytes:
    """Export TopOpt H8 element densities with 1-voxel zero halo as VTK ImageData (.vti)."""
    with np.load(io.BytesIO(density_payload), allow_pickle=False) as archive:
        densities = np.asarray(archive["densities_phys"], dtype="<f4")
        voxel_shape = np.asarray(archive["voxel_shape"], dtype=np.int32)
        origin = np.asarray(archive["voxel_origin"], dtype=np.float64)
        pitch = np.asarray(archive["voxel_pitch"], dtype=np.float64)
        active_ijk = np.asarray(archive["active_voxel_ijk"], dtype=np.int32)

    nx, ny, nz = int(voxel_shape[0]), int(voxel_shape[1]), int(voxel_shape[2])
    if nx <= 0 or ny <= 0 or nz <= 0:
        raise InvalidGeometryError("TopOpt density voxel grid must have positive dimensions.")

    padded = np.zeros((nx + 2, ny + 2, nz + 2), dtype="<f4")
    padded[active_ijk[:, 0] + 1, active_ijk[:, 1] + 1, active_ijk[:, 2] + 1] = densities
    # VTK ImageData uses Fortran ordering (X fastest, then Y, then Z)
    flat_f = np.ascontiguousarray(padded.ravel(order="F"), dtype="<f4")
    blob = _encode_vtk_zlib_block(flat_f)

    # Shifted origin aligns padded index (1,1,1) with physical voxel (0,0,0) center
    img_origin = origin - 0.5 * pitch
    extent = f"0 {nx + 1} 0 {ny + 1} 0 {nz + 1}"
    origin_str = f"{img_origin[0]:.9g} {img_origin[1]:.9g} {img_origin[2]:.9g}"
    spacing_str = f"{pitch[0]:.9g} {pitch[1]:.9g} {pitch[2]:.9g}"

    header_xml = (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="ImageData" version="0.1" byte_order="LittleEndian" '
        'header_type="UInt32" compressor="vtkZLibDataCompressor">\n'
        f'  <ImageData WholeExtent="{extent}" Origin="{origin_str}" Spacing="{spacing_str}">\n'
        f'    <Piece Extent="{extent}">\n'
        '      <PointData Scalars="density">\n'
        '        <DataArray type="Float32" Name="density" '
        'NumberOfComponents="1" format="appended" offset="0"/>\n'
        "      </PointData>\n"
        "      <CellData/>\n"
        "    </Piece>\n"
        "  </ImageData>\n"
        '  <AppendedData encoding="raw">\n_'
    ).encode("ascii")

    return header_xml + blob + b"\n  </AppendedData>\n</VTKFile>\n"


def _build_vtp_bytes(
    *,
    points: NDArray[np.float32],
    connectivity: NDArray[np.int32],
    offsets: NDArray[np.int32],
    n_verts: int,
    n_polys: int,
    point_arrays: list[tuple[str, NDArray[np.generic], int]],
    cell_arrays: list[tuple[str, NDArray[np.generic], int]],
    default_scalars: str = "",
    default_vectors: str = "",
) -> bytes:
    appended_chunks: list[bytes] = []
    current_offset = 0

    def _register(name: str, arr: NDArray[np.generic], n_comp: int) -> str:
        nonlocal current_offset
        vtk_type = _resolve_vtk_type(arr)
        blob = _encode_vtk_zlib_block(arr)
        tag = (
            f'<DataArray type="{vtk_type}" Name="{escape(name)}" '
            f'NumberOfComponents="{n_comp}" format="appended" offset="{current_offset}"/>'
        )
        appended_chunks.append(blob)
        current_offset += len(blob)
        return tag

    points_tag = _register("Points", points, 3)
    conn_tag = _register("connectivity", connectivity, 1)
    offsets_tag = _register("offsets", offsets, 1)
    pd_tags = "\n".join(_register(n, a, c) for n, a, c in point_arrays)
    cd_tags = "\n".join(_register(n, a, c) for n, a, c in cell_arrays)

    pd_attrs = f' Scalars="{escape(default_scalars)}"' if default_scalars else ""
    if default_vectors:
        pd_attrs += f' Vectors="{escape(default_vectors)}"'

    header_xml = (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian" '
        'header_type="UInt32" compressor="vtkZLibDataCompressor">\n'
        "  <PolyData>\n"
        f'    <Piece NumberOfPoints="{n_verts}" NumberOfVerts="0" '
        f'NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="{n_polys}">\n'
        f"      <PointData{pd_attrs}>\n"
        f"        {pd_tags}\n"
        "      </PointData>\n"
        "      <CellData>\n"
        f"        {cd_tags}\n"
        "      </CellData>\n"
        "      <Points>\n"
        f"        {points_tag}\n"
        "      </Points>\n"
        "      <Polys>\n"
        f"        {conn_tag}\n"
        f"        {offsets_tag}\n"
        "      </Polys>\n"
        "    </Piece>\n"
        "  </PolyData>\n"
        '  <AppendedData encoding="raw">\n_'
    ).encode("ascii")

    return header_xml + b"".join(appended_chunks) + b"\n  </AppendedData>\n</VTKFile>\n"


def _compact_surface_triangles(
    mesh: VolumeMeshData,
) -> tuple[NDArray[np.int32], NDArray[np.int32], NDArray[np.int32]]:
    if len(mesh.surface_triangles) == 0:
        raise InvalidGeometryError("Volume mesh has no exterior surface triangles to export.")
    used_nodes = np.unique(mesh.surface_triangles).astype("<i4")
    remap = np.full(len(mesh.nodes), -1, dtype="<i4")
    remap[used_nodes] = np.arange(len(used_nodes), dtype="<i4")
    surf_tris = np.ascontiguousarray(remap[mesh.surface_triangles], dtype="<i4")
    return used_nodes, remap, surf_tris


def _resolve_vtk_type(arr: NDArray[np.generic]) -> str:
    vtk_type = _VTK_TYPE_MAP.get(arr.dtype.name)
    if vtk_type is None:
        raise DomainValidationError(f"Unsupported numpy dtype for VTK XML: {arr.dtype.name}")
    return vtk_type


def _encode_vtk_zlib_block(arr: NDArray[np.generic]) -> bytes:
    """Encode a contiguous array using VTK UInt32 single-block vtkZLibDataCompressor header."""
    raw = np.ascontiguousarray(arr).tobytes()
    if not raw:
        return struct.pack("<3I", 0, 0, 0)
    compressed = zlib.compress(raw, level=6)
    header = struct.pack("<4I", 1, len(raw), len(raw), len(compressed))
    return header + compressed
