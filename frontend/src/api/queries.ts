import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { apiClient } from "@/api/apiClient";
import type {
  FemStudyCreateRequest,
  TopOptStudyCreateRequest,
  UnitSystem,
} from "@/api/types";
import { sceneRegistry } from "@/engine/sceneRegistry";

export const queryKeys = {
  health: ["health"] as const,
  materials: (u: UnitSystem) => ["materials", u] as const,
  projects: ["projects"] as const,
  geometries: (pid: string) => ["geometries", pid] as const,
  meshes: (pid: string) => ["meshes", pid] as const,
  jobs: (pid: string) => ["jobs", pid] as const,
  job: (jid: string) => ["job", jid] as const,
  femSummary: (jid: string) => ["fem-summary", jid] as const,
  topoptSummary: (jid: string) => ["topopt-summary", jid] as const,
  topoptHistory: (jid: string) => ["topopt-history", jid] as const,
};

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: apiClient.getHealth,
    refetchInterval: 30_000,
  });
}

export function useMaterialsQuery(unitSystem: UnitSystem) {
  return useQuery({
    queryKey: queryKeys.materials(unitSystem),
    queryFn: () => apiClient.listMaterials(unitSystem),
    staleTime: 5 * 60_000,
  });
}

export function useProjectsQuery() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: apiClient.listProjects,
  });
}

export function useCreateProjectMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { name: string; description: string }) =>
      apiClient.createProject(p.name, p.description),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export function useGeometriesQuery(projectId: string | null) {
  return useQuery({
    queryKey: projectId ? queryKeys.geometries(projectId) : ["geometries", "none"],
    queryFn: () => apiClient.listGeometries(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useUploadGeometryMutation(projectId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      file: File;
      unitSystem: UnitSystem;
      axisConvention: "Z_up" | "Y_up";
      autoRepair: boolean;
    }) => apiClient.uploadGeometry({ projectId: projectId!, ...params }),
    onSuccess: () => {
      if (projectId) {
        return qc.invalidateQueries({ queryKey: queryKeys.geometries(projectId) });
      }
      return undefined;
    },
  });
}

export function useMeshesQuery(projectId: string | null) {
  return useQuery({
    queryKey: projectId ? queryKeys.meshes(projectId) : ["meshes", "none"],
    queryFn: () => apiClient.listMeshes(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useGenerateMeshMutation(projectId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      geometryId: string;
      elementType: "H8" | "C3D4" | "C3D10";
      targetElementSize: number;
    }) => apiClient.generateMesh({ projectId: projectId!, ...params }),
    onSuccess: () => {
      if (projectId) {
        return qc.invalidateQueries({ queryKey: queryKeys.meshes(projectId) });
      }
      return undefined;
    },
  });
}

export function useJobsQuery(projectId: string | null) {
  return useQuery({
    queryKey: projectId ? queryKeys.jobs(projectId) : ["jobs", "none"],
    queryFn: () => apiClient.listJobs(projectId!),
    enabled: Boolean(projectId),
    refetchInterval: 4_000,
  });
}

export function useSubmitFemMutation(projectId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FemStudyCreateRequest) =>
      apiClient.submitFemStudy(projectId!, body),
    onSuccess: () => {
      if (projectId) {
        return qc.invalidateQueries({ queryKey: queryKeys.jobs(projectId) });
      }
      return undefined;
    },
  });
}

export function useSubmitTopOptMutation(projectId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TopOptStudyCreateRequest) =>
      apiClient.submitTopOptStudy(projectId!, body),
    onSuccess: () => {
      if (projectId) {
        return qc.invalidateQueries({ queryKey: queryKeys.jobs(projectId) });
      }
      return undefined;
    },
  });
}

export function useCancelJobMutation(projectId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiClient.cancelJob(jobId),
    onSuccess: () => {
      if (projectId) {
        return qc.invalidateQueries({ queryKey: queryKeys.jobs(projectId) });
      }
      return undefined;
    },
  });
}

export function useFemSummaryQuery(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: jobId ? queryKeys.femSummary(jobId) : ["fem-summary", "none"],
    queryFn: () => apiClient.getFemSummary(jobId!),
    enabled: Boolean(jobId && enabled),
  });
}

export function useTopOptSummaryQuery(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: jobId ? queryKeys.topoptSummary(jobId) : ["topopt-summary", "none"],
    queryFn: () => apiClient.getTopOptSummary(jobId!),
    enabled: Boolean(jobId && enabled),
  });
}

export function useTopOptHistoryQuery(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: jobId ? queryKeys.topoptHistory(jobId) : ["topopt-history", "none"],
    queryFn: () => apiClient.getTopOptHistory(jobId!),
    enabled: Boolean(jobId && enabled),
  });
}

/**
 * Subscribe to the revision integer for a resource key in the off-React registry.
 */
export function useSceneResourceRevision(key: string | null): number {
  useSyncExternalStore(sceneRegistry.subscribe, sceneRegistry.getSnapshot);
  return sceneRegistry.getRevision(key);
}

/**
 * Fetches binary .glb directly into SceneResourceRegistry and returns ONLY lightweight key handle.
 */
export function useLoadGlbResource(params: {
  key: string | null;
  fetcher: (() => Promise<ArrayBuffer>) | null;
  enabled: boolean;
}) {
  return useQuery({
    queryKey: ["binary-glb", params.key],
    queryFn: async () => {
      const k = params.key!;
      const existing = sceneRegistry.get(k);
      if (existing && existing.kind === "r3f-mesh") {
        return { key: k, revision: sceneRegistry.getRevision(k) };
      }
      const ab = await params.fetcher!();
      await sceneRegistry.registerGlbBuffer(k, ab);
      return { key: k, revision: sceneRegistry.getRevision(k) };
    },
    enabled: Boolean(params.enabled && params.key && params.fetcher),
    staleTime: Infinity,
    gcTime: 0,
  });
}

export function useLoadFemVtpResource(
  jobId: string | null,
  loadCaseId: string | null,
  enabled: boolean,
) {
  const key = jobId && loadCaseId ? `fem-vtp:${jobId}:${loadCaseId}` : null;
  return useQuery({
    queryKey: ["binary-vtp", key],
    queryFn: async () => {
      const k = key!;
      const existing = sceneRegistry.get(k);
      if (existing && existing.kind === "vtk-fem") {
        return { key: k, revision: sceneRegistry.getRevision(k) };
      }
      const ab = await apiClient.fetchFemResultsVtp(jobId!, loadCaseId!);
      sceneRegistry.registerFemVtpBuffer(k, ab);
      return { key: k, revision: sceneRegistry.getRevision(k) };
    },
    enabled: Boolean(enabled && key),
    staleTime: Infinity,
    gcTime: 0,
  });
}

export function useLoadTopOptVtiResource(jobId: string | null, enabled: boolean) {
  const key = jobId ? `topopt-vti:${jobId}` : null;
  return useQuery({
    queryKey: ["binary-vti", key],
    queryFn: async () => {
      const k = key!;
      const existing = sceneRegistry.get(k);
      if (existing && existing.kind === "vtk-vti") {
        return { key: k, revision: sceneRegistry.getRevision(k) };
      }
      const ab = await apiClient.fetchTopOptDensitiesVti(jobId!);
      sceneRegistry.registerTopOptVtiBuffer(k, ab);
      return { key: k, revision: sceneRegistry.getRevision(k) };
    },
    enabled: Boolean(enabled && key),
    staleTime: Infinity,
    gcTime: 0,
  });
}
