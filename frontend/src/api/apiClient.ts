import type {
  ErrorEnvelope,
  FemResultSummaryResponse,
  FemStudyCreateRequest,
  GeometryAssetResponse,
  HealthResponse,
  JobResponse,
  MaterialPreset,
  ProjectResponse,
  TopOptHistoryResponse,
  TopOptResultSummaryResponse,
  TopOptStudyCreateRequest,
  UnitSystem,
  VolumeMeshResponse,
} from "@/api/types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as Partial<ErrorEnvelope> & { detail?: string };
    if (body.code && body.message) {
      return new ApiError(res.status, body.code, body.message, body.details ?? {});
    }
    return new ApiError(res.status, "http_error", body.detail ?? res.statusText);
  } catch {
    return new ApiError(res.status, "http_error", res.statusText || "Request failed");
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as T;
}

async function fetchBinary(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url);
  if (!res.ok) {
    throw await parseError(res);
  }
  return await res.arrayBuffer();
}

export const apiClient = {
  getHealth: () => fetchJson<HealthResponse>("/api/v1/health"),

  listMaterials: (unitSystem: UnitSystem) =>
    fetchJson<MaterialPreset[]>(`/api/v1/materials?unit_system=${unitSystem}`),

  listProjects: () => fetchJson<ProjectResponse[]>("/api/v1/projects"),

  createProject: (name: string, description: string) =>
    fetchJson<ProjectResponse>("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    }),

  listGeometries: (projectId: string) =>
    fetchJson<GeometryAssetResponse[]>(`/api/v1/projects/${projectId}/geometries`),

  uploadGeometry: (params: {
    projectId: string;
    file: File;
    unitSystem: UnitSystem;
    axisConvention: "Z_up" | "Y_up";
    autoRepair: boolean;
  }) => {
    const fd = new FormData();
    fd.append("file", params.file);
    fd.append("unit_system", params.unitSystem);
    fd.append("axis_convention", params.axisConvention);
    fd.append("auto_repair", String(params.autoRepair));
    return fetchJson<GeometryAssetResponse>(
      `/api/v1/projects/${params.projectId}/geometries/upload`,
      { method: "POST", body: fd },
    );
  },

  fetchGeometryPreviewGlb: (geometryId: string) =>
    fetchBinary(`/api/v1/geometries/${geometryId}/preview.glb`),

  listMeshes: (projectId: string) =>
    fetchJson<VolumeMeshResponse[]>(`/api/v1/projects/${projectId}/meshes`),

  generateMesh: (params: {
    projectId: string;
    geometryId: string;
    elementType: "H8" | "C3D4" | "C3D10";
    targetElementSize: number;
  }) =>
    fetchJson<VolumeMeshResponse>(`/api/v1/projects/${params.projectId}/meshes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        geometry_id: params.geometryId,
        element_type: params.elementType,
        target_element_size: params.targetElementSize,
      }),
    }),

  fetchMeshSurfaceGlb: (meshId: string) =>
    fetchBinary(`/api/v1/meshes/${meshId}/surface.glb`),

  listJobs: (projectId: string) =>
    fetchJson<JobResponse[]>(`/api/v1/projects/${projectId}/jobs`),

  getJob: (jobId: string) => fetchJson<JobResponse>(`/api/v1/jobs/${jobId}`),

  cancelJob: (jobId: string) =>
    fetchJson<JobResponse>(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" }),

  submitFemStudy: (projectId: string, body: FemStudyCreateRequest) =>
    fetchJson<JobResponse>(`/api/v1/projects/${projectId}/studies/fem`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  submitTopOptStudy: (projectId: string, body: TopOptStudyCreateRequest) =>
    fetchJson<JobResponse>(`/api/v1/projects/${projectId}/studies/topopt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getFemSummary: (jobId: string) =>
    fetchJson<FemResultSummaryResponse>(`/api/v1/jobs/${jobId}/fem-summary`),

  fetchFemResultsVtp: (jobId: string, loadCaseId: string) =>
    fetchBinary(`/api/v1/jobs/${jobId}/fem-results/${loadCaseId}.vtp`),

  getTopOptSummary: (jobId: string) =>
    fetchJson<TopOptResultSummaryResponse>(`/api/v1/jobs/${jobId}/topopt-summary`),

  getTopOptHistory: (jobId: string) =>
    fetchJson<TopOptHistoryResponse>(`/api/v1/jobs/${jobId}/topopt-history`),

  fetchTopOptDensitiesVti: (jobId: string) =>
    fetchBinary(`/api/v1/jobs/${jobId}/topopt-densities.vti`),

  fetchTopOptReconstructedGlb: (jobId: string) =>
    fetchBinary(`/api/v1/jobs/${jobId}/reconstructed.glb`),
};
