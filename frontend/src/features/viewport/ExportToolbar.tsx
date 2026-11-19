import { Download } from "lucide-react";

import type { StudyType } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/useT";

export interface ExportToolbarProps {
  jobId: string | null;
  studyType: StudyType | null;
  loadCaseId: string | null;
  isCompleted: boolean;
}

export function ExportToolbar({
  jobId,
  studyType,
  loadCaseId,
  isCompleted,
}: ExportToolbarProps) {
  const t = useT();
  if (!jobId || !isCompleted) return null;

  const triggerDownload = (href: string) => {
    const a = document.createElement("a");
    a.href = href;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {studyType === "static_fem" && loadCaseId && (
        <>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              triggerDownload(`/api/v1/jobs/${jobId}/fem-results/${loadCaseId}.vtu`)
            }
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadVtu")}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              triggerDownload(`/api/v1/jobs/${jobId}/fem-results/${loadCaseId}.vtp`)
            }
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadVtp")}</span>
          </Button>
        </>
      )}

      {studyType === "topology_optimization" && (
        <>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerDownload(`/api/v1/jobs/${jobId}/topopt-results.vtu`)}
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadVtu")}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerDownload(`/api/v1/jobs/${jobId}/topopt-densities.vti`)}
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadVti")}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerDownload(`/api/v1/jobs/${jobId}/reconstructed-stl`)}
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadStl")}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerDownload(`/api/v1/jobs/${jobId}/reconstructed.glb`)}
          >
            <Download className="h-3 w-3" aria-hidden="true" />
            <span>{t("downloadGlb")}</span>
          </Button>
        </>
      )}
    </div>
  );
}
