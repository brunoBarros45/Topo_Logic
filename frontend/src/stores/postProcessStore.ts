import { create } from "zustand";

import type { ColormapName } from "@/engine/colormaps";

export type ScalarFieldName = "von_mises" | "displacement_magnitude" | "safety_factor";
export type TopOptViewMode = "vti_isosurface" | "reconstructed_glb";

export interface ClipAxisState {
  enabled: boolean;
  ratio: number; // 0..1 across bounding box axis
}

export interface ProbeReading {
  pointId: number;
  position: [number, number, number];
  value: number;
  field: ScalarFieldName;
  unit: string;
}

export interface PostProcessState {
  activeLoadCaseId: string | null;
  scalarField: ScalarFieldName;
  colormap: ColormapName;
  autoRange: boolean;
  manualMin: number;
  manualMax: number;
  deformScale: number;
  animateDeform: boolean;
  showGhostWireframe: boolean;
  clipX: ClipAxisState;
  clipY: ClipAxisState;
  clipZ: ClipAxisState;
  densityThreshold: number;
  topOptViewMode: TopOptViewMode;
  probeReading: ProbeReading | null;
  drawerOpen: boolean;

  setActiveLoadCaseId: (id: string | null) => void;
  setScalarField: (field: ScalarFieldName) => void;
  setColormap: (cmap: ColormapName) => void;
  setAutoRange: (auto: boolean) => void;
  setManualRange: (minVal: number, maxVal: number) => void;
  setDeformScale: (scale: number) => void;
  setAnimateDeform: (animate: boolean) => void;
  setShowGhostWireframe: (show: boolean) => void;
  setClipAxis: (axis: "clipX" | "clipY" | "clipZ", patch: Partial<ClipAxisState>) => void;
  setDensityThreshold: (threshold: number) => void;
  setTopOptViewMode: (mode: TopOptViewMode) => void;
  setProbeReading: (reading: ProbeReading | null) => void;
  setDrawerOpen: (open: boolean) => void;
}

export const usePostProcessStore = create<PostProcessState>((set) => ({
  activeLoadCaseId: null,
  scalarField: "von_mises",
  colormap: "turbo",
  autoRange: true,
  manualMin: 0,
  manualMax: 100,
  deformScale: 10,
  animateDeform: false,
  showGhostWireframe: true,
  clipX: { enabled: false, ratio: 0.5 },
  clipY: { enabled: false, ratio: 0.5 },
  clipZ: { enabled: false, ratio: 0.5 },
  densityThreshold: 0.5,
  topOptViewMode: "vti_isosurface",
  probeReading: null,
  drawerOpen: true,

  setActiveLoadCaseId: (activeLoadCaseId) => set({ activeLoadCaseId }),
  setScalarField: (scalarField) => set({ scalarField, probeReading: null }),
  setColormap: (colormap) => set({ colormap }),
  setAutoRange: (autoRange) => set({ autoRange }),
  setManualRange: (manualMin, manualMax) => set({ manualMin, manualMax }),
  setDeformScale: (deformScale) => set({ deformScale }),
  setAnimateDeform: (animateDeform) => set({ animateDeform }),
  setShowGhostWireframe: (showGhostWireframe) => set({ showGhostWireframe }),
  setClipAxis: (axis, patch) =>
    set((s) => ({
      [axis]: { ...s[axis], ...patch },
    })),
  setDensityThreshold: (densityThreshold) => set({ densityThreshold }),
  setTopOptViewMode: (topOptViewMode) => set({ topOptViewMode }),
  setProbeReading: (probeReading) => set({ probeReading }),
  setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
}));
