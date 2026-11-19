import { Crosshair } from "lucide-react";

import { getColormapCssGradient } from "@/engine/colormaps";
import { useT } from "@/i18n/useT";
import { usePostProcessStore } from "@/stores/postProcessStore";

export interface ColorbarLegendProps {
  minVal: number;
  maxVal: number;
  unit: string;
}

export function ColorbarLegend({ minVal, maxVal, unit }: ColorbarLegendProps) {
  const t = useT();
  const { scalarField, colormap, probeReading } = usePostProcessStore();

  const label =
    scalarField === "von_mises"
      ? t("fieldVonMises")
      : scalarField === "displacement_magnitude"
        ? t("fieldDispMag")
        : t("fieldSafetyFactor");

  const ticks = [1, 0.75, 0.5, 0.25, 0].map((frac) => {
    const val = minVal + frac * (maxVal - minVal);
    return Number.isFinite(val) ? val.toPrecision(3) : "0";
  });

  return (
    <div className="pointer-events-auto absolute bottom-3 right-3 z-20 flex flex-col gap-2">
      {probeReading && (
        <div
          role="status"
          className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-panel)]/95 px-2.5 py-1.5 text-[11px] shadow-lg backdrop-blur"
        >
          <div className="flex items-center gap-1.5 font-medium text-[var(--accent-primary)]">
            <Crosshair className="h-3 w-3" aria-hidden="true" />
            <span>
              {t("probeValue")} (#{probeReading.pointId})
            </span>
          </div>
          <div className="font-mono-tech font-semibold mt-0.5">
            {probeReading.value.toPrecision(4)} {probeReading.unit}
          </div>
        </div>
      )}

      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-panel)]/90 px-2.5 py-2 text-[11px] shadow-lg backdrop-blur">
        <div className="font-medium mb-1.5 text-[var(--text-primary)]">
          {label} ({unit})
        </div>
        <div className="flex items-stretch gap-2">
          <div
            className="w-3.5 h-32 rounded border border-[var(--border-subtle)]"
            style={{ background: getColormapCssGradient(colormap, "to top") }}
            aria-label={`${label} colorbar`}
          />
          <div className="flex flex-col justify-between font-mono-tech text-[10px] text-[var(--text-muted)]">
            {ticks.map((tk, i) => (
              <span key={i}>{tk}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
