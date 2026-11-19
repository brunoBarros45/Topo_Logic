export type UnitSystem = "mm_N_MPa" | "m_N_Pa";
export type AxisConvention = "Z_up" | "Y_up";
export type GeometryFormat = "stl" | "obj" | "ply" | "step";
export type ElementType = "H8" | "C3D4" | "C3D10";
export type SolverKind = "auto" | "direct" | "pcg_amg";
export type FilterKind = "cone_density" | "heaviside_projection";
export type OptimizerKind = "oc" | "mma";
export type SupportType = "fixed" | "displacement";
export type DesignZoneType = "passive_solid" | "passive_void";
export type StudyType = "static_fem" | "topology_optimization";
export type JobStatus =
  | "pending"
  | "meshing"
  | "solving"
  | "optimizing"
  | "reconstructing"
  | "completed"
  | "cancelled"
  | "failed";

export interface HealthResponse {
  status: string;
  version: string;
  execution_mode: string;
  supported_formats: GeometryFormat[];
}

export interface MaterialPreset {
  id: string;
  name: string;
  youngs_modulus: number;
  poissons_ratio: number;
  yield_strength: number;
  density: number;
  density_kg_m3: number;
  unit_system: UnitSystem;
  stress_unit: string;
  density_unit: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface BoundingBox3D {
  min_corner: [number, number, number];
  max_corner: [number, number, number];
  size: [number, number, number];
  center: [number, number, number];
  diagonal: number;
}

export interface ScaleGuardWarning {
  is_suspicious: boolean;
  message: string | null;
  suggested_unit_system: UnitSystem | null;
  suggested_scale_factor: number | null;
}

export interface MeshDiagnosticsResponse {
  vertex_count: number;
  triangle_count: number;
  connected_components: number;
  is_watertight: boolean;
  boundary_edge_count: number;
  non_manifold_edge_count: number;
  volume: number;
  surface_area: number;
  bounds: BoundingBox3D;
  scale_guard: ScaleGuardWarning;
  warnings: string[];
}

export interface RepairReportResponse {
  applied: boolean;
  merged_vertices_count: number;
  removed_degenerate_faces: number;
  removed_duplicate_faces: number;
  filled_holes: boolean;
  normals_fixed: boolean;
  warnings: string[];
}

export interface GeometryAssetResponse {
  id: string;
  project_id: string;
  filename: string;
  format: GeometryFormat;
  unit_system: UnitSystem;
  axis_convention: AxisConvention;
  has_repaired_artifact: boolean;
  diagnostics: MeshDiagnosticsResponse;
  repair_report: RepairReportResponse;
  created_at: string;
}

export interface VolumeMeshResponse {
  id: string;
  project_id: string;
  geometry_id: string;
  element_type: ElementType;
  node_count: number;
  element_count: number;
  surface_triangle_count: number;
  total_volume: number;
  min_scaled_jacobian: number;
  created_at: string;
}

export type RegionSelectorSchema =
  | {
      kind: "triangle_set";
      triangle_indices: number[];
      crease_angle_deg: number;
    }
  | {
      kind: "plane";
      point: [number, number, number];
      normal: [number, number, number];
      tolerance: number;
    }
  | {
      kind: "bounding_box";
      min_corner: [number, number, number];
      max_corner: [number, number, number];
    }
  | {
      kind: "cad_face_tag";
      face_tags: string[];
    };

export interface BoundaryRegionSchema {
  id: string;
  name: string;
  selector: RegionSelectorSchema;
}

export interface SupportBCSchema {
  region_id: string;
  support_type: SupportType;
  restrained_dofs?: [boolean, boolean, boolean];
  prescribed_displacement?: [number, number, number];
}

export type LoadDefinitionSchema =
  | {
      kind: "force";
      region_id: string;
      force_vector: [number, number, number];
    }
  | {
      kind: "pressure";
      region_id: string;
      magnitude: number;
    };

export interface LoadCaseSchema {
  id: string;
  name: string;
  weight: number;
  loads: LoadDefinitionSchema[];
}

export interface DesignZoneSchema {
  region_id: string;
  zone_type: DesignZoneType;
}

export interface StressConstraintSchema {
  enabled: boolean;
  max_von_mises: number | null;
  p_norm_exponent: number;
  use_adaptive_scaling: boolean;
}

export type MaterialInputSchema =
  | {
      preset_id: string;
    }
  | {
      name: string;
      youngs_modulus: number;
      poissons_ratio: number;
      yield_strength: number;
      density: number;
    };

export interface FemStudyCreateRequest {
  geometry_id: string;
  mesh_id: string;
  unit_system: UnitSystem;
  material: MaterialInputSchema;
  regions: BoundaryRegionSchema[];
  supports: SupportBCSchema[];
  load_cases: LoadCaseSchema[];
  element_type: ElementType;
  solver_kind: SolverKind;
}

export interface TopOptStudyCreateRequest {
  geometry_id: string;
  mesh_id: string;
  unit_system: UnitSystem;
  material: MaterialInputSchema;
  regions: BoundaryRegionSchema[];
  supports: SupportBCSchema[];
  load_cases: LoadCaseSchema[];
  element_type: ElementType;
  solver_kind: SolverKind;
  target_volume_fraction: number;
  penalty: number;
  e_min_ratio: number;
  filter_kind: FilterKind;
  filter_radius_ratio: number;
  optimizer_kind: OptimizerKind;
  move_limit: number;
  max_iterations: number;
  convergence_tol: number;
  use_continuation: boolean;
  stress_constraint: StressConstraintSchema;
  design_zones: DesignZoneSchema[];
}

export interface JobResponse {
  id: string;
  project_id: string;
  study_type: StudyType;
  status: JobStatus;
  progress: number;
  message: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface FieldStatsResponse {
  min_value: number;
  max_value: number;
  mean_value: number;
  unit: string;
}

export interface EquilibriumCheckResponse {
  force_residual_norm: number;
  applied_force_norm: number;
  relative_force_error: number;
  moment_residual_norm: number;
  is_balanced: boolean;
}

export interface LoadCaseFemSummaryResponse {
  load_case_id: string;
  compliance: number;
  displacement_stats: FieldStatsResponse;
  von_mises_stats: FieldStatsResponse;
  min_safety_factor: number;
  equilibrium: EquilibriumCheckResponse;
}

export interface FemResultSummaryResponse {
  job_id: string;
  mesh_id: string | null;
  load_case_results: LoadCaseFemSummaryResponse[];
}

export interface WeightSavingsResponse {
  original_mass_kg: number;
  optimized_mass_kg: number;
  mass_saved_kg: number;
  original_mass_g: number;
  optimized_mass_g: number;
  mass_saved_g: number;
  mass_reduction_percent: number;
}

export interface TopOptResultSummaryResponse {
  job_id: string;
  mesh_id: string | null;
  iterations_completed: number;
  converged: boolean;
  final_compliance: number;
  final_volume_fraction: number;
  weight_savings: WeightSavingsResponse | null;
}

export interface TopOptIterationPoint {
  iteration: number;
  compliance: number;
  volume_fraction: number;
  max_density_change: number;
  max_von_mises: number | null;
  strain_energy: number | null;
  remaining_mass_kg: number | null;
}

export interface TopOptHistoryResponse {
  job_id: string;
  points: TopOptIterationPoint[];
}

export interface JobWsFrame {
  event_type: string;
  job_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  payload: Record<string, unknown>;
}

export interface ErrorEnvelope {
  code: string;
  message: string;
  details: Record<string, unknown>;
}
