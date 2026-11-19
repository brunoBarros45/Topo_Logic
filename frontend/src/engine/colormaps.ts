import type vtkColorTransferFunction from "@kitware/vtk.js/Rendering/Core/ColorTransferFunction";

export type ColormapName = "turbo" | "viridis" | "coolwarm" | "plasma";

type ColorStop = readonly [number, number, number, number]; // [t in 0..1, r, g, b in 0..1]

const COLORMAP_STOPS: Record<ColormapName, readonly ColorStop[]> = {
  turbo: [
    [0.0, 0.18995, 0.07176, 0.23217],
    [0.125, 0.27628, 0.42118, 0.89123],
    [0.25, 0.15844, 0.73551, 0.92305],
    [0.375, 0.19659, 0.94901, 0.59466],
    [0.5, 0.64362, 0.98999, 0.23356],
    [0.625, 0.93301, 0.81236, 0.22667],
    [0.75, 0.98486, 0.49102, 0.12867],
    [0.875, 0.82297, 0.19283, 0.02116],
    [1.0, 0.4796, 0.01583, 0.01055],
  ],
  viridis: [
    [0.0, 0.267004, 0.004874, 0.329415],
    [0.143, 0.275191, 0.194905, 0.496005],
    [0.286, 0.212395, 0.359683, 0.55171],
    [0.429, 0.153364, 0.497, 0.557724],
    [0.571, 0.122312, 0.633153, 0.530398],
    [0.714, 0.288921, 0.758394, 0.428426],
    [0.857, 0.626579, 0.854645, 0.223353],
    [1.0, 0.993248, 0.906157, 0.143936],
  ],
  coolwarm: [
    [0.0, 0.229805, 0.298717, 0.753683],
    [0.25, 0.553594, 0.688995, 0.995375],
    [0.5, 0.865395, 0.86541, 0.865396],
    [0.75, 0.958852, 0.607645, 0.487877],
    [1.0, 0.705673, 0.015556, 0.150232],
  ],
  plasma: [
    [0.0, 0.050383, 0.029803, 0.527975],
    [0.2, 0.371238, 0.023508, 0.651205],
    [0.4, 0.653194, 0.130669, 0.591481],
    [0.6, 0.85769, 0.35785, 0.409052],
    [0.8, 0.979644, 0.619426, 0.233638],
    [1.0, 0.940015, 0.975158, 0.131326],
  ],
};

export function sampleColormapRgb(t: number, cmap: ColormapName): [number, number, number] {
  const clamped = Math.min(Math.max(t, 0), 1);
  const stops = COLORMAP_STOPS[cmap];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, r0, g0, b0] = stops[i];
    const [t1, r1, g1, b1] = stops[i + 1];
    if (clamped >= t0 && clamped <= t1) {
      const alpha = t1 > t0 ? (clamped - t0) / (t1 - t0) : 0;
      return [
        r0 + alpha * (r1 - r0),
        g0 + alpha * (g1 - g0),
        b0 + alpha * (b1 - b0),
      ];
    }
  }
  const last = stops[stops.length - 1];
  return [last[1], last[2], last[3]];
}

export function getColormapCssGradient(cmap: ColormapName, direction = "to top"): string {
  const stops = COLORMAP_STOPS[cmap].map(([t, r, g, b]) => {
    const pct = (t * 100).toFixed(1);
    return `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)}) ${pct}%`;
  });
  return `linear-gradient(${direction}, ${stops.join(", ")})`;
}

export function applyColormapToTransferFunction(
  ctf: vtkColorTransferFunction,
  minVal: number,
  maxVal: number,
  cmap: ColormapName,
): void {
  ctf.removeAllPoints();
  const lo = Number.isFinite(minVal) ? minVal : 0;
  const hi = Number.isFinite(maxVal) && maxVal > lo ? maxVal : lo + 1e-6;
  const span = hi - lo;
  for (const [t, r, g, b] of COLORMAP_STOPS[cmap]) {
    ctf.addRGBPoint(lo + t * span, r, g, b);
  }
}
