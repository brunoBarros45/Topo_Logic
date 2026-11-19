"""End-to-end API integration tests for Topo_Logic FastAPI routes and WebSockets."""

from __future__ import annotations

import io
import time

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from tests.fixtures_stl import make_cube_stl_bytes
from topo_logic.domain import StudyType
from topo_logic.interfaces.api.dependencies import AppContainer


@pytest.mark.integration
def test_health_projects_and_stl_upload_download_flow(app_client: TestClient) -> None:
    health_resp = app_client.get("/api/v1/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "ok"
    assert health_data["execution_mode"] == "local_first"
    assert health_data["supported_formats"] == ["stl"]

    proj_resp = app_client.post(
        "/api/v1/projects",
        json={"name": "Cantilever Bracket", "description": "Phase 1 API test"},
    )
    assert proj_resp.status_code == 201
    project = proj_resp.json()
    project_id = project["id"]

    list_resp = app_client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Upload binary STL under mm_N_MPa
    stl_bytes = make_cube_stl_bytes(25.0, binary=True)
    upload_resp = app_client.post(
        f"/api/v1/projects/{project_id}/geometries/upload",
        files={"file": ("bracket.stl", stl_bytes, "application/octet-stream")},
        data={"unit_system": "mm_N_MPa", "axis_convention": "Z_up", "auto_repair": "true"},
    )
    assert upload_resp.status_code == 201
    geom = upload_resp.json()
    geom_id = geom["id"]
    assert geom["format"] == "stl"
    assert geom["has_repaired_artifact"] is True
    assert geom["diagnostics"]["is_watertight"] is True
    assert geom["diagnostics"]["volume"] == pytest.approx(25.0**3, rel=1e-4)
    assert geom["diagnostics"]["scale_guard"]["is_suspicious"] is False

    # Download repaired binary STL and verify parseable
    dl_resp = app_client.get(f"/api/v1/geometries/{geom_id}/download?variant=repaired")
    assert dl_resp.status_code == 200
    parsed = trimesh.load(io.BytesIO(dl_resp.content), file_type="stl", force="mesh")
    assert isinstance(parsed, trimesh.Trimesh)
    assert parsed.is_watertight

    # Fetch geometry list & single metadata
    geom_get = app_client.get(f"/api/v1/geometries/{geom_id}")
    assert geom_get.status_code == 200
    assert geom_get.json()["id"] == geom_id

    geom_list = app_client.get(f"/api/v1/projects/{project_id}/geometries")
    assert geom_list.status_code == 200
    assert len(geom_list.json()) == 1


@pytest.mark.integration
def test_api_error_envelopes_and_job_websocket_snapshot(app_client: TestClient) -> None:
    proj_resp = app_client.post("/api/v1/projects", json={"name": "Error & WS Test"})
    project_id = proj_resp.json()["id"]

    # Unsupported .obj upload in Phase 1 returns standardized 415 ErrorEnvelope
    obj_resp = app_client.post(
        f"/api/v1/projects/{project_id}/geometries/upload",
        files={"file": ("part.obj", b"v 0 0 0\n", "text/plain")},
    )
    assert obj_resp.status_code == 415
    assert obj_resp.json()["code"] == "unsupported_format"

    # Non-existent project returns 404 ErrorEnvelope
    missing_resp = app_client.get("/api/v1/projects/does-not-exist")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["code"] == "resource_not_found"

    # Job cancellation + WebSocket snapshot check
    container: AppContainer = app_client.app.state.container  # type: ignore[attr-defined]
    job = container.job_service.create_job(project_id=project_id, study_type=StudyType.STATIC_FEM)

    cancel_resp = app_client.post(f"/api/v1/jobs/{job.id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    with app_client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["event_type"] == "job.snapshot"
        assert snapshot["job_id"] == job.id
        assert snapshot["status"] == "cancelled"


@pytest.mark.integration
def test_materials_preset_endpoints(app_client: TestClient) -> None:
    resp_mm = app_client.get("/api/v1/materials")
    assert resp_mm.status_code == 200
    presets_mm = resp_mm.json()
    assert len(presets_mm) == 5
    steel_mm = next(item for item in presets_mm if item["id"] == "steel_aisi_1020")
    assert steel_mm["unit_system"] == "mm_N_MPa"
    assert steel_mm["stress_unit"] == "MPa"
    assert steel_mm["density_unit"] == "tonne/mm^3"
    assert steel_mm["youngs_modulus"] == pytest.approx(205_000.0)
    assert steel_mm["density_kg_m3"] == pytest.approx(7870.0)

    resp_si = app_client.get("/api/v1/materials?unit_system=m_N_Pa")
    assert resp_si.status_code == 200
    steel_si = next(item for item in resp_si.json() if item["id"] == "steel_aisi_1020")
    assert steel_si["unit_system"] == "m_N_Pa"
    assert steel_si["stress_unit"] == "Pa"
    assert steel_si["density_unit"] == "kg/m^3"
    assert steel_si["youngs_modulus"] == pytest.approx(205e9)
    assert steel_si["density"] == pytest.approx(7870.0)

    alu_resp = app_client.get("/api/v1/materials/aluminum_6061_t6")
    assert alu_resp.status_code == 200
    assert alu_resp.json()["name"] == "Aluminum 6061-T6"

    missing_resp = app_client.get("/api/v1/materials/unknown_mat")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["code"] == "resource_not_found"


@pytest.mark.integration
def test_end_to_end_stl_mesh_fem_and_binary_fields_flow(app_client: TestClient) -> None:
    proj_id = app_client.post("/api/v1/projects", json={"name": "Beam E2E"}).json()["id"]

    beam = trimesh.creation.box(extents=(100.0, 10.0, 10.0))
    beam.apply_translation((50.0, 5.0, 5.0))
    beam_raw = beam.export(file_type="stl")
    beam_bytes = beam_raw if isinstance(beam_raw, bytes) else bytes(beam_raw)

    upload_resp = app_client.post(
        f"/api/v1/projects/{proj_id}/geometries/upload",
        files={"file": ("beam.stl", beam_bytes, "application/octet-stream")},
        data={"unit_system": "mm_N_MPa", "axis_convention": "Z_up", "auto_repair": "true"},
    )
    assert upload_resp.status_code == 201
    geom_id = upload_resp.json()["id"]

    # Generate H8 volumetric mesh
    mesh_resp = app_client.post(
        f"/api/v1/projects/{proj_id}/meshes",
        json={"geometry_id": geom_id, "element_type": "H8", "target_element_size": 5.0},
    )
    assert mesh_resp.status_code == 201
    mesh = mesh_resp.json()
    mesh_id = mesh["id"]
    assert mesh["element_type"] == "H8"
    assert mesh["element_count"] == 80  # 20 x 2 x 2
    assert mesh["total_volume"] == pytest.approx(10_000.0)

    surface_resp = app_client.get(f"/api/v1/meshes/{mesh_id}/surface")
    assert surface_resp.status_code == 200
    surface = surface_resp.json()
    assert surface["node_count"] == mesh["node_count"]
    assert len(surface["surface_triangles"]) == mesh["surface_triangle_count"]

    # Submit multi-loadcase static FEM study
    fem_req = {
        "geometry_id": geom_id,
        "mesh_id": mesh_id,
        "unit_system": "mm_N_MPa",
        "material": {"preset_id": "steel_aisi_1020"},
        "regions": [
            {
                "id": "r-root",
                "name": "Root Clamp",
                "selector": {
                    "kind": "plane",
                    "point": [0.0, 0.0, 0.0],
                    "normal": [1.0, 0.0, 0.0],
                    "tolerance": 1e-4,
                },
            },
            {
                "id": "r-tip",
                "name": "Tip Face",
                "selector": {
                    "kind": "plane",
                    "point": [100.0, 0.0, 0.0],
                    "normal": [1.0, 0.0, 0.0],
                    "tolerance": 1e-4,
                },
            },
        ],
        "supports": [{"region_id": "r-root", "support_type": "fixed"}],
        "load_cases": [
            {
                "id": "lc-bend",
                "name": "Tip Shear",
                "loads": [
                    {"kind": "force", "region_id": "r-tip", "force_vector": [0.0, 0.0, -50.0]}
                ],
            },
            {
                "id": "lc-axial",
                "name": "Tip Pressure",
                "loads": [{"kind": "pressure", "region_id": "r-tip", "magnitude": -5.0}],
            },
        ],
        "element_type": "H8",
        "solver_kind": "auto",
    }
    study_resp = app_client.post(f"/api/v1/projects/{proj_id}/studies/fem", json=fem_req)
    assert study_resp.status_code == 202
    job_id = study_resp.json()["id"]

    # Poll until background worker completes
    deadline = time.monotonic() + 10.0
    job_status = study_resp.json()["status"]
    while job_status not in {"completed", "failed", "cancelled"}:
        assert time.monotonic() < deadline, "Timed out waiting for FEM job completion"
        time.sleep(0.025)
        job_status = app_client.get(f"/api/v1/jobs/{job_id}").json()["status"]

    assert job_status == "completed"

    summary_resp = app_client.get(f"/api/v1/jobs/{job_id}/fem-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert len(summary["load_case_results"]) == 2
    for lc in summary["load_case_results"]:
        assert lc["equilibrium"]["is_balanced"] is True
        assert lc["von_mises_stats"]["max_value"] > 0.0

    # Download packed little-endian Float32 Von Mises buffer
    vm_resp = app_client.get(f"/api/v1/jobs/{job_id}/fields/lc-bend?field=von_mises")
    assert vm_resp.status_code == 200
    assert vm_resp.headers["X-Topo-Dtype"] == "float32"
    assert vm_resp.headers["X-Topo-Unit"] == "MPa"
    vm_arr = np.frombuffer(vm_resp.content, dtype="<f4")
    assert len(vm_arr) == mesh["node_count"]
    assert float(np.max(vm_arr)) == pytest.approx(
        summary["load_case_results"][0]["von_mises_stats"]["max_value"], rel=1e-5
    )

    # Download vector displacement Float32 buffer (N_nodes, 3)
    disp_resp = app_client.get(f"/api/v1/jobs/{job_id}/fields/lc-bend?field=displacement")
    assert disp_resp.status_code == 200
    assert disp_resp.headers["X-Topo-Shape"] == f"{mesh['node_count']},3"
    disp_arr = np.frombuffer(disp_resp.content, dtype="<f4").reshape(-1, 3)
    assert disp_arr.shape == (mesh["node_count"], 3)
