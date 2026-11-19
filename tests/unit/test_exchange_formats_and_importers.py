"""Unit tests for binary VTK XML (.vtp/.vti/.vtu), .glb exporters, and multi-format importers."""

from __future__ import annotations

import io
import shutil
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np
import pytest
import trimesh

from tests.fixtures_stl import make_cube_stl_bytes
from topo_logic.application.ports.geometry import RawSurfacePayload
from topo_logic.domain.exceptions import DomainValidationError
from topo_logic.domain.geometry import ElementType, GeometryFormat
from topo_logic.infrastructure.exporters import (
    export_fem_surface_vtp,
    export_fem_volume_vtu,
    export_mesh_surface_vtp,
    export_stl_to_glb,
    export_topopt_densities_vti,
    export_volume_surface_to_glb,
)
from topo_logic.infrastructure.mesh import (
    CompositeGeometryImporter,
    GmshStepImporter,
    TrimeshSurfaceImporter,
    VoxelH8Mesher,
    deserialize_volume_mesh,
    parse_msh2_text,
)


def _decode_vtk_xml_binary(
    vtk_bytes: bytes,
) -> tuple[ET.Element, dict[str, tuple[np.ndarray, int]]]:
    """Parse VTK XML header and decompress every AppendedData raw zlib block."""
    marker = b'<AppendedData encoding="raw">\n_'
    idx = vtk_bytes.index(marker)
    footer = b"\n  </AppendedData>"
    end_idx = vtk_bytes.index(footer, idx + len(marker))

    header_xml = vtk_bytes[:idx].decode("ascii") + "</VTKFile>"
    raw_appended = vtk_bytes[idx + len(marker) : end_idx]
    root = ET.fromstring(header_xml)

    dtype_map = {"Float32": np.float32, "Int32": np.int32, "UInt8": np.uint8}
    arrays: dict[str, tuple[np.ndarray, int]] = {}
    for el in root.iter("DataArray"):
        if el.attrib.get("format") != "appended":
            continue
        name = el.attrib["Name"]
        n_comp = int(el.attrib.get("NumberOfComponents", "1"))
        offset = int(el.attrib["offset"])
        n_blocks, _bs, _lbs, comp_size = struct.unpack_from("<4I", raw_appended, offset)
        assert n_blocks == 1
        start = offset + 16
        decompressed = zlib.decompress(raw_appended[start : start + comp_size])
        np_dtype = dtype_map[el.attrib["type"]]
        arr = np.frombuffer(decompressed, dtype=np_dtype)
        arrays[name] = (arr, n_comp)
    return root, arrays


@pytest.mark.unit
def test_vtk_xml_vtp_vtu_vti_and_glb_roundtrip() -> None:
    stl_bytes = make_cube_stl_bytes(10.0, binary=True)
    _summary, mesh_payload = VoxelH8Mesher().generate_volume_mesh(
        stl_bytes,
        geometry_id="geom-vtk",
        element_type=ElementType.H8,
        target_element_size=5.0,
    )
    mesh = deserialize_volume_mesh(mesh_payload)

    # 1. Surface .vtp + .glb parity
    surf_vtp = export_mesh_surface_vtp(mesh)
    root_vtp, arrays_vtp = _decode_vtk_xml_binary(surf_vtp)
    assert root_vtp.attrib["type"] == "PolyData"
    pts_arr, pts_comp = arrays_vtp["Points"]
    assert pts_comp == 3
    assert len(pts_arr) // 3 == len(np.unique(mesh.surface_triangles))
    assert len(arrays_vtp["connectivity"][0]) == len(mesh.surface_triangles) * 3
    assert np.all(arrays_vtp["original_node_id"][0] == np.unique(mesh.surface_triangles))

    # 2. FEM surface .vtp & volume .vtu
    n_nodes = len(mesh.nodes)
    disp = np.ones((n_nodes, 3), dtype="<f4") * 0.25
    vm = np.linspace(1.0, 50.0, n_nodes, dtype="<f4")
    fem_vtp = export_fem_surface_vtp(mesh, {"displacement": disp, "von_mises": vm})
    _, fem_vtp_arr = _decode_vtk_xml_binary(fem_vtp)
    assert fem_vtp_arr["von_mises"][0].max() == pytest.approx(50.0, rel=1e-5)
    assert fem_vtp_arr["displacement"][1] == 3

    fem_vtu = export_fem_volume_vtu(mesh, point_fields={"von_mises": vm})
    root_vtu, fem_vtu_arr = _decode_vtk_xml_binary(fem_vtu)
    assert root_vtu.attrib["type"] == "UnstructuredGrid"
    assert np.all(fem_vtu_arr["types"][0] == 12)  # VTK_HEXAHEDRON
    assert len(fem_vtu_arr["connectivity"][0]) == len(mesh.elements) * 8

    # 3. TopOpt .vti (2x2x2 active voxels -> 4x4x4 with 1-voxel zero halo in Fortran order)
    buf = io.BytesIO()
    assert mesh.voxel_shape == (2, 2, 2)
    assert mesh.voxel_origin is not None
    assert mesh.voxel_pitch is not None
    assert mesh.active_voxel_ijk is not None
    np.savez_compressed(
        buf,
        densities_phys=np.full(len(mesh.elements), 0.75, dtype=np.float32),
        densities_raw=np.full(len(mesh.elements), 0.75, dtype=np.float32),
        voxel_shape=np.asarray(mesh.voxel_shape, dtype=np.int32),
        voxel_origin=np.asarray(mesh.voxel_origin, dtype=np.float64),
        voxel_pitch=np.asarray(mesh.voxel_pitch, dtype=np.float64),
        active_voxel_ijk=np.asarray(mesh.active_voxel_ijk, dtype=np.int32),
    )
    vti_bytes = export_topopt_densities_vti(buf.getvalue())
    root_vti, vti_arr = _decode_vtk_xml_binary(vti_bytes)
    assert root_vti.attrib["type"] == "ImageData"
    img_el = root_vti.find("ImageData")
    assert img_el is not None
    assert img_el.attrib["WholeExtent"] == "0 3 0 3 0 3"
    dens_3d = vti_arr["density"][0].reshape((4, 4, 4), order="F")
    assert np.all(dens_3d[1:3, 1:3, 1:3] == pytest.approx(0.75))
    assert np.all(dens_3d[0, :, :] == 0.0)
    assert np.all(dens_3d[-1, :, :] == 0.0)

    # 4. Binary .glb exports start with glTF magic header and parse back cleanly
    stl_glb = export_stl_to_glb(stl_bytes)
    mesh_glb = export_volume_surface_to_glb(mesh)
    assert stl_glb[:4] == b"glTF"
    assert mesh_glb[:4] == b"glTF"
    scene_or_mesh = trimesh.load(io.BytesIO(mesh_glb), file_type="glb", force="mesh")
    assert isinstance(scene_or_mesh, trimesh.Trimesh)
    assert len(scene_or_mesh.faces) == len(mesh.surface_triangles)


@pytest.mark.unit
def test_vtu_c3d10_cell_type_24() -> None:
    msh2_sample = "\n".join(
        [
            "$MeshFormat",
            "2.2 0 8",
            "$EndMeshFormat",
            "$Nodes",
            "10",
            "1 0 0 0",
            "2 1 0 0",
            "3 0 1 0",
            "4 0 0 1",
            "5 0.5 0 0",
            "6 0.5 0.5 0",
            "7 0 0.5 0",
            "8 0 0 0.5",
            "9 0 0.5 0.5",
            "10 0.5 0 0.5",
            "$EndNodes",
            "$Elements",
            "1",
            "1 11 2 0 1 1 2 3 4 5 6 7 8 9 10",
            "$EndElements",
        ]
    )
    _, payload = parse_msh2_text(
        msh2_sample, geometry_id="tet-10", element_type=ElementType.C3D10
    )
    mesh = deserialize_volume_mesh(payload)
    vtu_bytes = export_fem_volume_vtu(mesh)
    _, arrays = _decode_vtk_xml_binary(vtu_bytes)
    assert np.all(arrays["types"][0] == 24)  # VTK_QUADRATIC_TETRA
    assert len(arrays["connectivity"][0]) == 10


@pytest.mark.unit
def test_multi_format_importers_obj_ply_and_step(monkeypatch: pytest.MonkeyPatch) -> None:
    box = trimesh.creation.box(extents=(12.0, 10.0, 8.0))
    obj_raw = box.export(file_type="obj")
    ply_raw = box.export(file_type="ply")
    obj_bytes = obj_raw.encode("utf-8") if isinstance(obj_raw, str) else bytes(obj_raw)
    ply_bytes = ply_raw if isinstance(ply_raw, bytes) else bytes(ply_raw)

    surf_importer = TrimeshSurfaceImporter()
    for ext, fmt, data in (
        ("box.obj", GeometryFormat.OBJ, obj_bytes),
        ("box.ply", GeometryFormat.PLY, ply_bytes),
    ):
        stl_out = surf_importer.extract_surface_stl(
            RawSurfacePayload(raw_bytes=data, filename=ext, format=fmt)
        )
        parsed = trimesh.load(io.BytesIO(stl_out), file_type="stl", force="mesh")
        assert isinstance(parsed, trimesh.Trimesh)
        assert parsed.is_watertight
        assert parsed.volume == pytest.approx(960.0, rel=1e-4)

    # Missing Gmsh CLI raises actionable DomainValidationError
    monkeypatch.setattr(shutil, "which", lambda _exe: None)
    step_importer = GmshStepImporter()
    with pytest.raises(DomainValidationError, match="Gmsh CLI"):
        step_importer.extract_surface_stl(
            RawSurfacePayload(
                raw_bytes=b"ISO-10303-21;",
                filename="cad.step",
                format=GeometryFormat.STEP,
            )
        )

    # Mocked Gmsh CLI subprocess converts STEP -> binary STL cleanly
    monkeypatch.setattr(shutil, "which", lambda _exe: "C:/mock/gmsh.exe")
    fake_stl = make_cube_stl_bytes(5.0, binary=True)

    class _Proc:
        returncode = 0
        stderr = ""

    def _fake_run(cmd: list[str], **_kwargs: object) -> _Proc:
        out_path = Path(cmd[-1])
        out_path.write_bytes(fake_stl)
        return _Proc()

    monkeypatch.setattr(
        "topo_logic.infrastructure.mesh.multi_format_importer.subprocess.run",
        _fake_run,
    )
    composite = CompositeGeometryImporter([surf_importer, step_importer])
    assert composite.supported_formats() == {
        GeometryFormat.STL,
        GeometryFormat.OBJ,
        GeometryFormat.PLY,
        GeometryFormat.STEP,
    }
    step_stl = composite.extract_surface_stl(
        RawSurfacePayload(
            raw_bytes=b"ISO-10303-21;",
            filename="bracket.stp",
            format=GeometryFormat.STEP,
        )
    )
    assert step_stl == fake_stl
