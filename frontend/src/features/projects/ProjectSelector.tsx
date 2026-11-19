import { FolderPlus } from "lucide-react";
import { useEffect, useId, useMemo, useState, type FormEvent } from "react";

import { useCreateProjectMutation, useProjectsQuery } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { NativeDialog } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { useT } from "@/i18n/useT";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function ProjectSelector() {
  const t = useT();
  const { activeProjectId, setActiveProjectId, announce } = useWorkspaceStore();
  const projectsQuery = useProjectsQuery();
  const createMutation = useCreateProjectMutation();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const selectId = useId();
  const nameId = useId();
  const nameErrId = useId();
  const descId = useId();

  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data],
  );

  useEffect(() => {
    if (!activeProjectId && projects.length > 0) {
      setActiveProjectId(projects[0].id);
    }
  }, [activeProjectId, projects, setActiveProjectId]);

  const showNameError = (nameTouched || submitAttempted) && name.trim().length < 2;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (name.trim().length < 2) return;
    const created = await createMutation.mutateAsync({
      name: name.trim(),
      description: description.trim(),
    });
    setActiveProjectId(created.id);
    announce(`${t("project")}: ${created.name}`);
    setName("");
    setDescription("");
    setNameTouched(false);
    setSubmitAttempted(false);
    setOpen(false);
  };

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={selectId} className="visually-hidden">
        {t("project")}
      </label>
      <NativeSelect
        id={selectId}
        aria-label={t("project")}
        value={activeProjectId ?? ""}
        onChange={(e) => setActiveProjectId(e.target.value || null)}
        className="w-48"
      >
        {projects.length === 0 ? (
          <option value="">— {t("newProject")} —</option>
        ) : (
          projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))
        )}
      </NativeSelect>

      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen(true)}
        data-testid="new-project-btn"
      >
        <FolderPlus className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{t("newProject")}</span>
      </Button>

      <NativeDialog open={open} onOpenChange={setOpen} title={t("newProject")}>
        <form onSubmit={handleSubmit} className="space-y-3" noValidate>
          <div>
            <Label htmlFor={nameId}>
              {t("projectName")} <span aria-hidden="true">*</span>
            </Label>
            <Input
              id={nameId}
              name="project_name"
              required
              autoFocus
              value={name}
              aria-invalid={showNameError}
              aria-describedby={showNameError ? nameErrId : undefined}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => setNameTouched(true)}
            />
            {showNameError && (
              <p id={nameErrId} role="alert" className="mt-1 text-[11px] text-red-400">
                Min. 2 characters.
              </p>
            )}
          </div>

          <div>
            <Label htmlFor={descId}>{t("projectDescription")}</Label>
            <Input
              id={descId}
              name="project_description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {t("create")}
            </Button>
          </div>
        </form>
      </NativeDialog>
    </div>
  );
}
