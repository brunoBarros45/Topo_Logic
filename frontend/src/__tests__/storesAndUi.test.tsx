import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConvergenceDrawer } from "@/features/analytics/ConvergenceDrawer";
import { ProjectSelector } from "@/features/projects/ProjectSelector";
import { usePostProcessStore } from "@/stores/postProcessStore";
import { useStudyBuilderStore } from "@/stores/studyBuilderStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

function wrapWithQuery(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function assertNoHeavyBinaryBuffers(value: unknown, path = "state"): void {
  if (value === null || typeof value !== "object") return;
  if (
    value instanceof ArrayBuffer ||
    ArrayBuffer.isView(value) ||
    typeof (value as { dispose?: unknown }).dispose === "function"
  ) {
    throw new Error(`Heavy binary/GPU object found inside Zustand at ${path}`);
  }
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (typeof v === "function") continue;
    assertNoHeavyBinaryBuffers(v, `${path}.${k}`);
  }
}

describe("Zustand stores & Theme/Locale compliance", () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="color-scheme" content="dark light" />';
    localStorage.clear();
  });

  it("never stores heavy typed arrays or GPU geometries inside React/Zustand stores", () => {
    assertNoHeavyBinaryBuffers(useWorkspaceStore.getState(), "workspace");
    assertNoHeavyBinaryBuffers(useStudyBuilderStore.getState(), "studyBuilder");
    assertNoHeavyBinaryBuffers(usePostProcessStore.getState(), "postProcess");
  });

  it("synchronizes locale to <html lang> and theme mode to <meta color-scheme> and localStorage", () => {
    const ws = useWorkspaceStore.getState();
    ws.setLocale("en");
    expect(document.documentElement.lang).toBe("en");
    ws.setLocale("es");
    expect(document.documentElement.lang).toBe("es");

    ws.setThemeMode("light");
    expect(
      document.querySelector('meta[name="color-scheme"]')?.getAttribute("content"),
    ).toBe("light");
    expect(localStorage.getItem("topo-color-scheme")).toBe("light");

    ws.setThemeMode("system");
    expect(
      document.querySelector('meta[name="color-scheme"]')?.getAttribute("content"),
    ).toBe("light dark");
    expect(localStorage.getItem("topo-color-scheme")).toBeNull();
  });
});

describe("UI Components & Recharts Analytics", () => {
  it("validates new project native <dialog> form on submit before posting", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(wrapWithQuery(<ProjectSelector />));
    const user = userEvent.setup();
    await user.click(screen.getByTestId("new-project-btn"));

    const submitBtn = screen.getByRole("button", { name: /Crear|Create/i });
    await user.click(submitBtn);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("renders Recharts TopOpt convergence drawer cleanly with iteration points", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
    render(
      wrapWithQuery(
        <ConvergenceDrawer
          overridePoints={[
            {
              iteration: 1,
              compliance: 120.5,
              volume_fraction: 0.4,
              max_density_change: 0.2,
              max_von_mises: 180.0,
              strain_energy: 60.25,
              remaining_mass_kg: 0.42,
            },
            {
              iteration: 2,
              compliance: 88.2,
              volume_fraction: 0.4,
              max_density_change: 0.04,
              max_von_mises: 145.0,
              strain_energy: 44.1,
              remaining_mass_kg: 0.42,
            },
          ]}
        />,
      ),
    );
    expect(screen.getByText(/\(2 iters\)/i)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
