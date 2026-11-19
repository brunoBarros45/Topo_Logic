import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { queryKeys } from "@/api/queries";
import type { JobStatus, JobWsFrame, TopOptIterationPoint } from "@/api/types";
import { useWorkspaceStore } from "@/stores/workspaceStore";

const TERMINAL: ReadonlySet<JobStatus> = new Set([
  "completed",
  "cancelled",
  "failed",
]);

export interface LiveJobStreamState {
  status: JobStatus | null;
  progress: number;
  message: string;
  liveIterations: TopOptIterationPoint[];
}

export function useJobStream(
  jobId: string | null,
  projectId: string | null,
  initialStatus: JobStatus | null,
): LiveJobStreamState {
  const qc = useQueryClient();
  const announce = useWorkspaceStore((s) => s.announce);

  const [state, setState] = useState<LiveJobStreamState>({
    status: initialStatus,
    progress: 0,
    message: "",
    liveIterations: [],
  });

  useEffect(() => {
    setState({
      status: initialStatus,
      progress: initialStatus === "completed" ? 1 : 0,
      message: "",
      liveIterations: [],
    });

    if (!jobId || (initialStatus && TERMINAL.has(initialStatus))) {
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/jobs/${jobId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (evt) => {
      try {
        const frame = JSON.parse(String(evt.data)) as JobWsFrame;
        if (frame.event_type === "topopt.iteration") {
          const p = frame.payload;
          const pt: TopOptIterationPoint = {
            iteration: Number(p.iteration ?? 0),
            compliance: Number(p.compliance ?? 0),
            volume_fraction: Number(p.volume_fraction ?? 0),
            max_density_change: Number(p.max_density_change ?? 0),
            max_von_mises:
              p.max_von_mises !== undefined && p.max_von_mises !== null
                ? Number(p.max_von_mises)
                : null,
            strain_energy:
              p.strain_energy !== undefined && p.strain_energy !== null
                ? Number(p.strain_energy)
                : 0.5 * Number(p.compliance ?? 0),
            remaining_mass_kg:
              p.remaining_mass_kg !== undefined && p.remaining_mass_kg !== null
                ? Number(p.remaining_mass_kg)
                : null,
          };
          setState((prev) => ({
            status: frame.status,
            progress: frame.progress,
            message: frame.message,
            liveIterations: [
              ...prev.liveIterations.filter((x) => x.iteration !== pt.iteration),
              pt,
            ].sort((a, b) => a.iteration - b.iteration),
          }));
          return;
        }

        setState((prev) => ({
          ...prev,
          status: frame.status,
          progress: frame.progress,
          message: frame.message,
        }));

        if (TERMINAL.has(frame.status)) {
          announce(`${frame.status}: ${frame.message}`);
          if (projectId) {
            void qc.invalidateQueries({ queryKey: queryKeys.jobs(projectId) });
          }
          void qc.invalidateQueries({ queryKey: queryKeys.femSummary(jobId) });
          void qc.invalidateQueries({ queryKey: queryKeys.topoptSummary(jobId) });
          void qc.invalidateQueries({ queryKey: queryKeys.topoptHistory(jobId) });
        }
      } catch {
        // Ignore malformed non-JSON frame
      }
    };

    return () => {
      ws.close();
    };
  }, [jobId, projectId, initialStatus, qc, announce]);

  return state;
}
