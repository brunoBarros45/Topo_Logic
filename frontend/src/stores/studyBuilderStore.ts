import { create } from "zustand";

import type {
  BoundaryRegionSchema,
  DesignZoneSchema,
  DesignZoneType,
  FilterKind,
  LoadCaseSchema,
  LoadDefinitionSchema,
  OptimizerKind,
  SolverKind,
  StressConstraintSchema,
  SupportBCSchema,
  UnitSystem,
} from "@/api/types";

export interface RegionWithColor extends BoundaryRegionSchema {
  color: string;
}

export type ActiveStudyMode = "static_fem" | "topology_optimization";

const REGION_PALETTE = [
  "#22c55e", // emerald support
  "#f59e0b", // amber load
  "#38bdf8", // sky zone
  "#ec4899", // pink zone
  "#a855f7", // purple zone
  "#14b8a6", // teal zone
];

export interface StudyBuilderState {
  unitSystem: UnitSystem;
  studyMode: ActiveStudyMode;
  solverKind: SolverKind;
  useCustomMaterial: boolean;
  materialPresetId: string;
  customMaterial: {
    name: string;
    youngs_modulus: number;
    poissons_ratio: number;
    yield_strength: number;
    density: number;
  };

  regions: RegionWithColor[];
  supports: SupportBCSchema[];
  loadCases: LoadCaseSchema[];
  designZones: DesignZoneSchema[];

  // Flood-fill picking state
  pickingActive: boolean;
  pickingRegionName: string;
  creaseAngleDeg: number;
  highlightedRegionId: string | null;

  // TopOpt parameters
  targetVolumeFraction: number;
  penalty: number;
  filterKind: FilterKind;
  filterRadiusRatio: number;
  optimizerKind: OptimizerKind;
  moveLimit: number;
  maxIterations: number;
  useContinuation: boolean;
  stressConstraint: StressConstraintSchema;

  setUnitSystem: (u: UnitSystem) => void;
  setStudyMode: (m: ActiveStudyMode) => void;
  setSolverKind: (s: SolverKind) => void;
  setUseCustomMaterial: (custom: boolean) => void;
  setMaterialPresetId: (id: string) => void;
  setCustomMaterialField: (
    field: keyof StudyBuilderState["customMaterial"],
    val: string | number,
  ) => void;
  setPickingActive: (active: boolean) => void;
  setPickingRegionName: (name: string) => void;
  setCreaseAngleDeg: (deg: number) => void;
  setHighlightedRegionId: (id: string | null) => void;

  addFloodFillRegion: (name: string, triangleIndices: number[], creaseDeg: number) => string;
  addPlaneRegion: (
    name: string,
    point: [number, number, number],
    normal: [number, number, number],
    tolerance: number,
  ) => string;
  addBoxRegion: (
    name: string,
    minCorner: [number, number, number],
    maxCorner: [number, number, number],
  ) => string;
  removeRegion: (id: string) => void;

  addSupport: (regionId: string) => void;
  removeSupport: (index: number) => void;

  addLoad: (loadCaseId: string, load: LoadDefinitionSchema) => void;
  removeLoad: (loadCaseId: string, index: number) => void;
  addLoadCase: (name: string, weight?: number) => void;

  addDesignZone: (regionId: string, zoneType: DesignZoneType) => void;
  removeDesignZone: (index: number) => void;

  setTopOptField: <
    K extends
      | "targetVolumeFraction"
      | "penalty"
      | "filterKind"
      | "filterRadiusRatio"
      | "optimizerKind"
      | "moveLimit"
      | "maxIterations"
      | "useContinuation",
  >(
    key: K,
    val: StudyBuilderState[K],
  ) => void;
  setStressConstraint: (patch: Partial<StressConstraintSchema>) => void;
  loadCantileverPreset: (
    boundsMin: [number, number, number],
    boundsMax: [number, number, number],
  ) => void;
  resetStudy: () => void;
}

let seq = 1;
const nextId = (prefix: string): string => `${prefix}-${seq++}`;

export const useStudyBuilderStore = create<StudyBuilderState>((set) => ({
  unitSystem: "mm_N_MPa",
  studyMode: "static_fem",
  solverKind: "auto",
  useCustomMaterial: false,
  materialPresetId: "aluminum_6061_t6",
  customMaterial: {
    name: "Custom Alloy",
    youngs_modulus: 69000,
    poissons_ratio: 0.33,
    yield_strength: 275,
    density: 2.7e-9,
  },

  regions: [],
  supports: [],
  loadCases: [{ id: "lc-1", name: "Load Case 1", weight: 1.0, loads: [] }],
  designZones: [],

  pickingActive: false,
  pickingRegionName: "Selected Face",
  creaseAngleDeg: 22,
  highlightedRegionId: null,

  targetVolumeFraction: 0.4,
  penalty: 3.0,
  filterKind: "cone_density",
  filterRadiusRatio: 1.5,
  optimizerKind: "oc",
  moveLimit: 0.2,
  maxIterations: 25,
  useContinuation: true,
  stressConstraint: {
    enabled: false,
    max_von_mises: 180,
    p_norm_exponent: 8.0,
    use_adaptive_scaling: true,
  },

  setUnitSystem: (unitSystem) => set({ unitSystem }),
  setStudyMode: (studyMode) => set({ studyMode }),
  setSolverKind: (solverKind) => set({ solverKind }),
  setUseCustomMaterial: (useCustomMaterial) => set({ useCustomMaterial }),
  setMaterialPresetId: (materialPresetId) => set({ materialPresetId }),
  setCustomMaterialField: (field, val) =>
    set((s) => ({
      customMaterial: { ...s.customMaterial, [field]: val },
    })),
  setPickingActive: (pickingActive) => set({ pickingActive }),
  setPickingRegionName: (pickingRegionName) => set({ pickingRegionName }),
  setCreaseAngleDeg: (creaseAngleDeg) => set({ creaseAngleDeg }),
  setHighlightedRegionId: (highlightedRegionId) => set({ highlightedRegionId }),

  addFloodFillRegion: (name, triangleIndices, creaseDeg) => {
    const id = nextId("reg-face");
    set((s) => {
      const color = REGION_PALETTE[s.regions.length % REGION_PALETTE.length];
      return {
        highlightedRegionId: id,
        pickingActive: false,
        regions: [
          ...s.regions,
          {
            id,
            name: name.trim() || id,
            color,
            selector: {
              kind: "triangle_set",
              triangle_indices: triangleIndices,
              crease_angle_deg: creaseDeg,
            },
          },
        ],
      };
    });
    return id;
  },

  addPlaneRegion: (name, point, normal, tolerance) => {
    const id = nextId("reg-plane");
    set((s) => {
      const color = REGION_PALETTE[s.regions.length % REGION_PALETTE.length];
      return {
        highlightedRegionId: id,
        regions: [
          ...s.regions,
          {
            id,
            name: name.trim() || id,
            color,
            selector: { kind: "plane", point, normal, tolerance },
          },
        ],
      };
    });
    return id;
  },

  addBoxRegion: (name, minCorner, maxCorner) => {
    const id = nextId("reg-box");
    set((s) => {
      const color = REGION_PALETTE[s.regions.length % REGION_PALETTE.length];
      return {
        highlightedRegionId: id,
        regions: [
          ...s.regions,
          {
            id,
            name: name.trim() || id,
            color,
            selector: {
              kind: "bounding_box",
              min_corner: minCorner,
              max_corner: maxCorner,
            },
          },
        ],
      };
    });
    return id;
  },

  removeRegion: (id) =>
    set((s) => ({
      regions: s.regions.filter((r) => r.id !== id),
      supports: s.supports.filter((sup) => sup.region_id !== id),
      designZones: s.designZones.filter((dz) => dz.region_id !== id),
      loadCases: s.loadCases.map((lc) => ({
        ...lc,
        loads: lc.loads.filter((ld) => ld.region_id !== id),
      })),
      highlightedRegionId: s.highlightedRegionId === id ? null : s.highlightedRegionId,
    })),

  addSupport: (regionId) =>
    set((s) => ({
      supports: [
        ...s.supports,
        { region_id: regionId, support_type: "fixed", restrained_dofs: [true, true, true] },
      ],
    })),

  removeSupport: (index) =>
    set((s) => ({ supports: s.supports.filter((_, idx) => idx !== index) })),

  addLoad: (loadCaseId, load) =>
    set((s) => ({
      loadCases: s.loadCases.map((lc) =>
        lc.id === loadCaseId ? { ...lc, loads: [...lc.loads, load] } : lc,
      ),
    })),

  removeLoad: (loadCaseId, index) =>
    set((s) => ({
      loadCases: s.loadCases.map((lc) =>
        lc.id === loadCaseId
          ? { ...lc, loads: lc.loads.filter((_, idx) => idx !== index) }
          : lc,
      ),
    })),

  addLoadCase: (name, weight = 1.0) =>
    set((s) => ({
      loadCases: [
        ...s.loadCases,
        { id: nextId("lc"), name: name.trim() || `Load Case ${s.loadCases.length + 1}`, weight, loads: [] },
      ],
    })),

  addDesignZone: (regionId, zoneType) =>
    set((s) => ({ designZones: [...s.designZones, { region_id: regionId, zone_type: zoneType }] })),

  removeDesignZone: (index) =>
    set((s) => ({ designZones: s.designZones.filter((_, idx) => idx !== index) })),

  setTopOptField: (key, val) => set({ [key]: val } as Partial<StudyBuilderState>),

  setStressConstraint: (patch) =>
    set((s) => {
      const updated = { ...s.stressConstraint, ...patch };
      const optimizerKind = updated.enabled ? "mma" : s.optimizerKind;
      return { stressConstraint: updated, optimizerKind };
    }),

  loadCantileverPreset: (boundsMin, boundsMax) => {
    const [xmin, ymin, zmin] = boundsMin;
    const [xmax, ymax, zmax] = boundsMax;
    const dx = Math.max(xmax - xmin, 1);
    const tol = Math.max(dx * 1e-3, 1e-3);
    const rootId = "preset-root";
    const tipId = "preset-tip";
    set({
      regions: [
        {
          id: rootId,
          name: "Root Clamp (X min)",
          color: "#22c55e",
          selector: {
            kind: "plane",
            point: [xmin, 0.5 * (ymin + ymax), 0.5 * (zmin + zmax)],
            normal: [1, 0, 0],
            tolerance: tol,
          },
        },
        {
          id: tipId,
          name: "Tip Load Pad (X max)",
          color: "#f59e0b",
          selector: {
            kind: "bounding_box",
            min_corner: [xmax - tol, ymin, zmin],
            max_corner: [xmax + tol, ymax, zmin + 0.5 * (zmax - zmin) + tol],
          },
        },
      ],
      supports: [{ region_id: rootId, support_type: "fixed", restrained_dofs: [true, true, true] }],
      loadCases: [
        {
          id: "lc-1",
          name: "Cantilever Shear",
          weight: 1.0,
          loads: [{ kind: "force", region_id: tipId, force_vector: [0, 0, -500] }],
        },
      ],
      designZones: [],
      highlightedRegionId: rootId,
    });
  },

  resetStudy: () =>
    set({
      regions: [],
      supports: [],
      loadCases: [{ id: "lc-1", name: "Load Case 1", weight: 1.0, loads: [] }],
      designZones: [],
      highlightedRegionId: null,
    }),
}));
