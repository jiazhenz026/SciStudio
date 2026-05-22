import { useState } from "react";

import { api } from "../lib/api";
import type { ProjectResponse } from "../types/api";

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
      const result = await api.openNativeDialog("directory");
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

        <div className={`grid gap-4 ${mode === "new" ? "md:grid-cols-2" : ""}`}>
          <label className="grid gap-2 text-sm text-stone-700">
            <span className="font-medium">
              {mode === "new" ? "Project name" : "Project ID or path"}
            </span>
            {mode === "open" ? (
              <div className="flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
                  onChange={(event) => {
                    onChange({ path: event.target.value });
                    setPathError(null);
                  }}
                  placeholder="C:\\research\\atlas-project"
                  value={path}
                />
                <button
                  className="shrink-0 rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-600 transition hover:border-ember hover:text-ember"
                  onClick={() => void handleBrowse()}
                  type="button"
                >
                  Browse
                </button>
              </div>
            ) : (
              <input
                className="rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
                onChange={(event) => onChange({ name: event.target.value })}
                placeholder="Multimodal Atlas"
                value={name}
              />
            )}
          </label>
          {mode === "new" ? (
            <div className="grid gap-2 text-sm text-stone-700">
              <span className="font-medium">Parent directory</span>
              <div className="flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
                  onChange={(event) => {
                    onChange({ path: event.target.value });
                    setPathError(null);
                  }}
                  placeholder="C:\\projects"
                  value={path}
                />
                <button
                  className="shrink-0 rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-600 transition hover:border-ember hover:text-ember"
                  onClick={() => void handleBrowse()}
                  type="button"
                >
                  Browse
                </button>
              </div>
            </div>
          ) : null}
          {mode === "new" ? (
            <label className="grid gap-2 text-sm text-stone-700 md:col-span-2">
              <span className="font-medium">Description</span>
              <textarea
                className="min-h-28 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
                onChange={(event) => onChange({ description: event.target.value })}
                placeholder="Integrated IF, Raman, and LC-MS pilot."
                value={description}
              />
            </label>
          ) : null}
        </div>

        {pathError ? <p className="mt-2 text-sm text-red-600">{pathError}</p> : null}

        <div className="mt-6 rounded-[1.5rem] border border-stone-200 bg-white/80 p-4">
          <p className="text-xs uppercase tracking-[0.3em] text-stone-500">Recent projects</p>
          <div className="mt-3 flex max-h-64 flex-col gap-2 overflow-y-auto">
            {recentProjects.length ? (
              recentProjects.map((project) => (
                <button
                  className="flex items-center justify-between rounded-2xl border border-stone-200 px-4 py-3 text-left transition hover:border-pine hover:bg-pine/5"
                  key={project.id}
                  onClick={() => onOpenRecent(project.id)}
                  type="button"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-ink">{project.name}</span>
                    <span className="block truncate text-xs text-stone-500">{project.path}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="rounded-full bg-sand px-3 py-1 text-xs text-stone-700">
                      {project.workflow_count} workflow{project.workflow_count === 1 ? "" : "s"}
                    </span>
                    {onDeleteProject ? (
                      <span
                        className="rounded-full p-1 text-stone-400 transition hover:bg-red-50 hover:text-red-600"
                        onClick={(event) => handleDeleteProject(event, project.id, project.name)}
                        onKeyDown={() => {}}
                        role="button"
                        tabIndex={0}
                        title="Delete project"
                      >
                        <svg
                          className="size-4"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={2}
                          viewBox="0 0 24 24"
                        >
                          <path
                            d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </span>
                    ) : null}
                  </span>
                </button>
              ))
            ) : (
              <p className="text-sm text-stone-500">
                No project history yet. Create one to get started.
              </p>
            )}
          </div>
        </div>

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
