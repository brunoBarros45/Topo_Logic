import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const winBackendBin = path.join(repoRoot, ".venv", "Scripts", "topo-logic.exe");
const unixBackendBin = path.join(repoRoot, ".venv", "bin", "topo-logic");
const backendBin = fs.existsSync(winBackendBin)
  ? winBackendBin
  : fs.existsSync(unixBackendBin)
    ? unixBackendBin
    : "topo-logic";

const e2eDataDir =
  process.env.TOPO_E2E_DATA_DIR ??
  path.join(os.tmpdir(), `topo-logic-e2e-${Date.now()}`);
process.env.TOPO_E2E_DATA_DIR = e2eDataDir;
fs.mkdirSync(e2eDataDir, { recursive: true });

const reuseExistingServer =
  !process.env.CI && Boolean(process.env.TOPO_E2E_REUSE_SERVER);
const viteBin = path.join(__dirname, "node_modules", "vite", "bin", "vite.js");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    headless: true,
    launchOptions: {
      args: ["--use-gl=angle", "--use-angle=swiftshader"],
    },
  },
  webServer: [
    {
      command: `"${backendBin}" serve --host 127.0.0.1 --port 8000 --data-dir "${e2eDataDir}"`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `"${process.execPath}" "${viteBin}" --host 127.0.0.1 --port 5173 --strictPort`,
      cwd: __dirname,
      url: "http://127.0.0.1:5173/",
      reuseExistingServer,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
