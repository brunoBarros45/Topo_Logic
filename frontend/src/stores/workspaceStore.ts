import { create } from "zustand";

import type { Locale } from "@/i18n/translations";

export type ThemeMode = "dark" | "light" | "system";
export type SidebarTab = "model" | "physics" | "results";
export type ViewportMode = "setup" | "results" | "split";
export type SplitPreset = "setup_vs_results" | "job_vs_job";

const THEME_STORAGE_KEY = "topo-color-scheme";
const LOCALE_STORAGE_KEY = "topo-locale";

export function applyThemeToDocument(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const content = mode === "system" ? "light dark" : mode;
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.setAttribute("content", content);
  }
  const prefersDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = mode === "dark" || (mode === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", isDark);
}

function readInitialTheme(): ThemeMode {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
    if (raw === "light dark") return "system";
  } catch {
    // Ignore storage access errors in restricted frames
  }
  return "dark";
}

function readInitialLocale(): Locale {
  try {
    const raw = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (raw === "en" || raw === "es") return raw;
  } catch {
    // Ignore storage access errors
  }
  return "es";
}

export interface WorkspaceState {
  activeProjectId: string | null;
  activeGeometryId: string | null;
  activeMeshId: string | null;
  activeJobId: string | null;
  compareJobId: string | null;
  sidebarTab: SidebarTab;
  viewportMode: ViewportMode;
  splitPreset: SplitPreset;
  cameraSyncEnabled: boolean;
  themeMode: ThemeMode;
  locale: Locale;
  statusAnnouncement: string;

  setActiveProjectId: (projectId: string | null) => void;
  setActiveGeometryId: (geometryId: string | null) => void;
  setActiveMeshId: (meshId: string | null) => void;
  setActiveJobId: (jobId: string | null) => void;
  setCompareJobId: (jobId: string | null) => void;
  setSidebarTab: (tab: SidebarTab) => void;
  setViewportMode: (mode: ViewportMode) => void;
  setSplitPreset: (preset: SplitPreset) => void;
  setCameraSyncEnabled: (enabled: boolean) => void;
  setThemeMode: (mode: ThemeMode) => void;
  setLocale: (locale: Locale) => void;
  announce: (text: string) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeProjectId: null,
  activeGeometryId: null,
  activeMeshId: null,
  activeJobId: null,
  compareJobId: null,
  sidebarTab: "model",
  viewportMode: "setup",
  splitPreset: "setup_vs_results",
  cameraSyncEnabled: true,
  themeMode: readInitialTheme(),
  locale: readInitialLocale(),
  statusAnnouncement: "",

  setActiveProjectId: (activeProjectId) =>
    set({
      activeProjectId,
      activeGeometryId: null,
      activeMeshId: null,
      activeJobId: null,
      compareJobId: null,
    }),
  setActiveGeometryId: (activeGeometryId) =>
    set({ activeGeometryId, activeMeshId: null }),
  setActiveMeshId: (activeMeshId) => set({ activeMeshId }),
  setActiveJobId: (activeJobId) => set({ activeJobId }),
  setCompareJobId: (compareJobId) => set({ compareJobId }),
  setSidebarTab: (sidebarTab) => set({ sidebarTab }),
  setViewportMode: (viewportMode) => set({ viewportMode }),
  setSplitPreset: (splitPreset) => set({ splitPreset }),
  setCameraSyncEnabled: (cameraSyncEnabled) => set({ cameraSyncEnabled }),
  setThemeMode: (themeMode) => {
    try {
      if (themeMode === "system") {
        localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        localStorage.setItem(THEME_STORAGE_KEY, themeMode);
      }
    } catch {
      // Non-fatal
    }
    applyThemeToDocument(themeMode);
    set({ themeMode });
  },
  setLocale: (locale) => {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      // Non-fatal
    }
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
    set({ locale });
  },
  announce: (statusAnnouncement) => set({ statusAnnouncement }),
}));

export function syncThemeFromStorageEvent(event: StorageEvent): void {
  if (event.key !== THEME_STORAGE_KEY) return;
  const next: ThemeMode =
    event.newValue === "light" || event.newValue === "dark" ? event.newValue : "system";
  applyThemeToDocument(next);
  useWorkspaceStore.setState({ themeMode: next });
}
