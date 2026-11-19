import { expect, test } from "@playwright/test";

function makeBoxBinaryStl(lx = 50, ly = 20, lz = 20): Buffer {
  // 12 triangles for axis-aligned box [0, lx] x [0, ly] x [0, lz]
  const v: [number, number, number][] = [
    [0, 0, 0],
    [lx, 0, 0],
    [lx, ly, 0],
    [0, ly, 0],
    [0, 0, lz],
    [lx, 0, lz],
    [lx, ly, lz],
    [0, ly, lz],
  ];
  const tris: [number, number, number][] = [
    [0, 2, 1], [0, 3, 2],
    [4, 5, 6], [4, 6, 7],
    [0, 1, 5], [0, 5, 4],
    [1, 2, 6], [1, 6, 5],
    [2, 3, 7], [2, 7, 6],
    [3, 0, 4], [3, 4, 7],
  ];
  const buf = Buffer.alloc(84 + tris.length * 50);
  buf.write("Topo_Logic E2E Binary STL", 0, "ascii");
  buf.writeUInt32LE(tris.length, 80);
  tris.forEach(([i0, i1, i2], idx) => {
    const off = 84 + idx * 50;
    const pts = [v[i0], v[i1], v[i2]];
    // normal left 0; auto_repair fixes/checks normals
    buf.writeFloatLE(0, off);
    buf.writeFloatLE(0, off + 4);
    buf.writeFloatLE(0, off + 8);
    pts.forEach((p, k) => {
      buf.writeFloatLE(p[0], off + 12 + k * 12);
      buf.writeFloatLE(p[1], off + 16 + k * 12);
      buf.writeFloatLE(p[2], off + 20 + k * 12);
    });
  });
  return buf;
}

test("end-to-end CAE workflow: project -> STL -> H8 mesh -> FEM VTK.js -> TopOpt Recharts", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => {
    console.error("[E2E pageerror]", err);
    pageErrors.push(err.message);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      console.error("[E2E console.error]", msg.text());
    }
  });

  await page.goto("/");
  await expect(page.getByText(/v0\.4\./)).toBeVisible();

  // 1. Create Project
  await page.getByTestId("new-project-btn").click();
  await page.fill('input[name="project_name"]', "Playwright E2E Bracket");
  await page.getByRole("button", { name: /Crear|Create/i }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByLabel("Proyecto", { exact: true }).or(page.getByLabel("Project", { exact: true }))).toContainText("Playwright E2E Bracket");

  // 2. Upload Binary STL Box
  await page.getByTestId("geometry-file-input").setInputFiles({
    name: "cantilever_box.stl",
    mimeType: "application/octet-stream",
    buffer: makeBoxBinaryStl(50, 20, 20),
  });
  await expect(page.getByText(/Estanca|Watertight/i)).toBeVisible();

  // 3. Generate H8 Mesh
  await page.getByTestId("generate-mesh-btn").click();
  await expect(page.getByText(/Nodes:/i)).toBeVisible({ timeout: 15_000 });

  // 4. Switch to Physics tab -> Load Cantilever Preset -> Run Static FEM
  await page.getByRole("tab", { name: /Cargas|Loads/i }).click();
  await page.getByTestId("cantilever-preset-btn").click();
  await page.getByTestId("run-study-btn").click();

  await expect(page.getByText("COMPLETED").first()).toBeVisible({ timeout: 20_000 });

  // 5. Switch to VTK.js Results view & verify canvas + exports
  await page.getByTestId("viewport-mode-results").click();
  await expect(page.getByTestId("vtk-viewport-vtk-main")).toBeVisible();
  await expect(page.getByRole("button", { name: /\.vtu/i }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /\.vtp/i }).first()).toBeVisible({ timeout: 15_000 });

  // 6. Switch to TopOpt & verify Recharts + VTI export
  await page.getByRole("tab", { name: /Cargas|Loads/i }).click();
  const modeSelect = page.locator("select").filter({ hasText: /SIMP/i }).first();
  await modeSelect.selectOption("topology_optimization");
  await page.fill("#max-iters", "8");
  await page.getByTestId("run-study-btn").click();

  await expect(page.getByRole("button", { name: /\.vti/i })).toBeVisible({ timeout: 25_000 });
  await expect(page.getByRole("button", { name: /\.stl/i }).first()).toBeVisible();
  await expect(page.getByText(/iters\)/i)).toBeVisible({ timeout: 15_000 });

  expect(pageErrors).toEqual([]);
});
