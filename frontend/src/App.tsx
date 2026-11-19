import { Activity, Languages, Moon, Sun } from "lucide-react";
import { useEffect } from "react";

import { useHealthQuery } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConvergenceDrawer } from "@/features/analytics/ConvergenceDrawer";
import { GeometryPanel } from "@/features/geometry/GeometryPanel";
import { MeshingPanel } from "@/features/meshing/MeshingPanel";
import { ProjectSelector } from "@/features/projects/ProjectSelector";
import { JobsResultsPanel } from "@/features/results/JobsResultsPanel";
import { StudyBuilderPanel } from "@/features/study-builder/StudyBuilderPanel";
import { ViewportHost } from "@/features/viewport/ViewportHost";
import { useT } from "@/i18n/useT";
import {
  syncThemeFromStorageEvent,
  useWorkspaceStore,
  type SidebarTab,
} from "@/stores/workspaceStore";

export function App() {
  const t = useT();
  const {
    sidebarTab,
    themeMode,
    locale,
    statusAnnouncement,
    setSidebarTab,
    setThemeMode,
    setLocale,
  } = useWorkspaceStore();

  const healthQuery = useHealthQuery();

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    window.addEventListener("storage", syncThemeFromStorageEvent);
    return () => window.removeEventListener("storage", syncThemeFromStorageEvent);
  }, []);

  const cycleTheme = () => {
    const next = themeMode === "dark" ? "light" : themeMode === "light" ? "system" : "dark";
    setThemeMode(next);
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--bg-app)] text-[var(--text-primary)]">
      <a href="#workspace-main" className="skip-link visually-hidden">
        {t("skipToContent")}
      </a>

      <div aria-live="polite" className="visually-hidden">
        {statusAnnouncement}
      </div>

      {/* Top Engineering Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-panel)] px-4 py-2 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-[var(--accent-primary)] text-slate-950 font-bold text-xs">
              TL
            </span>
            <div>
              <h1 className="text-sm font-bold leading-none">{t("appName")}</h1>
              <p className="text-[10px] text-[var(--text-muted)]">{t("appTagline")}</p>
            </div>
          </div>

          <ProjectSelector />
        </div>

        <nav aria-label="Workspace Settings" className="flex items-center gap-2">
          {healthQuery.data ? (
            <Badge variant="success">
              <Activity className="h-3 w-3" aria-hidden="true" />
              <span>v{healthQuery.data.version}</span>
            </Badge>
          ) : (
            <Badge variant="warning">API Offline</Badge>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setLocale(locale === "es" ? "en" : "es")}
            aria-label={t("language")}
            data-testid="locale-toggle-btn"
          >
            <Languages className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{locale.toUpperCase()}</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={cycleTheme}
            aria-label={`${t("theme")}: ${themeMode}`}
            data-testid="theme-toggle-btn"
          >
            {themeMode === "light" ? (
              <Sun className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Moon className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            <span>
              {themeMode === "dark"
                ? t("themeDark")
                : themeMode === "light"
                  ? t("themeLight")
                  : t("themeSystem")}
            </span>
          </Button>
        </nav>
      </header>

      {/* Main Split CAE Workbench */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <aside
          aria-label="CAE Inspector"
          className="w-80 lg:w-96 shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-panel)] flex flex-col min-h-0"
        >
          <Tabs
            value={sidebarTab}
            onValueChange={(v) => setSidebarTab(v as SidebarTab)}
            className="flex flex-col h-full min-h-0 p-2.5"
          >
            <TabsList className="grid grid-cols-3 w-full shrink-0">
              <TabsTrigger value="model">{t("tabModel")}</TabsTrigger>
              <TabsTrigger value="physics">{t("tabPhysics")}</TabsTrigger>
              <TabsTrigger value="results">{t("tabResults")}</TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto cae-scroll pr-1 mt-2">
              <TabsContent value="model" className="space-y-3 mt-0">
                <GeometryPanel />
                <MeshingPanel />
              </TabsContent>
              <TabsContent value="physics" className="mt-0">
                <StudyBuilderPanel />
              </TabsContent>
              <TabsContent value="results" className="mt-0">
                <JobsResultsPanel />
              </TabsContent>
            </div>
          </Tabs>
        </aside>

        <main
          id="workspace-main"
          tabIndex={-1}
          className="flex flex-1 flex-col min-w-0 min-h-0 overflow-hidden"
        >
          <div className="flex-1 min-h-0">
            <ViewportHost />
          </div>
          <ConvergenceDrawer />
        </main>
      </div>
    </div>
  );
}

export default App;
