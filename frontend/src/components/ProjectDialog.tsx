import { useState } from "react";

import { api } from "../lib/api";
import type { ProjectResponse } from "../types/api";
import { ProjectFormFields } from "./ProjectDialog.parts/ProjectFormFields";
import { RecentProjectsList } from "./ProjectDialog.parts/RecentProjectsList";

interface ProjectDialogProps {
  open: boolean;
  mode: "new" | "open";
  name: string;
  description: string;
  path: string;
  recentProjects: ProjectResponse[];
  onClose: () => void;
  onChange: (patch: Partial<{ name: string; description: string; path: string }>) => void;
  onSubmit: () => void;
  onOpenRecent: (projectIdOrPath: string) => void;
  onDeleteProject?: (projectId: string) => void;
}

export function ProjectDialog({
  open,
  mode,
  name,
  description,
  path,
  recentProjects,
  onClose,
  onChange,
  onSubmit,
  onOpenRecent,
  onDeleteProject,
}: ProjectDialogProps) {
  const [pathError, setPathError] = useState<string | null>(null);

  if (!open) {
    return null;
  }

  async function handleBrowse() {
    try {
      // prefer_home: creating/opening a project picks a location outside any
      // project, so this dialog opens at home, not the active project root (#1915).
      const result = await api.openNativeDialog("directory", undefined, true);
      if (result.paths.length > 0) {
        onChange({ path: result.paths[0] });
        setPathError(null);
      }
    } catch {
      // Dialog cancelled or error — ignore
    }
  }

  function handleSubmit() {
    if (mode === "new" && !path.trim()) {
      setPathError("Parent directory is required");
      return;
    }
    if (mode === "open" && !path.trim()) {
      setPathError("Project path is required");
      return;
    }
    setPathError(null);
    onSubmit();
  }

  function handleDeleteProject(event: React.MouseEvent, projectId: string, projectName: string) {
    event.stopPropagation();
    if (
      onDeleteProject &&
      window.confirm(`Delete project '${projectName}'? This cannot be undone.`)
    ) {
      onDeleteProject(projectId);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-[2rem] border border-stone-200 bg-stone-50 p-6 shadow-panel">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Projects</p>
            <h2 className="mt-2 font-display text-3xl text-ink">
              {mode === "new" ? "Create a new workspace" : "Open an existing workspace"}
            </h2>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <ProjectFormFields
          mode={mode}
          name={name}
          description={description}
          path={path}
          onChange={onChange}
          onPathChangeClearError={() => setPathError(null)}
          onBrowse={() => void handleBrowse()}
        />

        {pathError ? <p className="mt-2 text-sm text-red-600">{pathError}</p> : null}

        <RecentProjectsList
          recentProjects={recentProjects}
          onOpenRecent={onOpenRecent}
          onDeleteProject={onDeleteProject}
          onDeleteClick={handleDeleteProject}
        />

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine"
            onClick={handleSubmit}
            type="button"
          >
            {mode === "new" ? "Create project" : "Open project"}
          </button>
        </div>
      </div>
    </div>
  );
}
