/**
 * Logo + active-project label inside the Toolbar. Extracted in #1413.
 */
import type { ProjectResponse } from "../../types/api";

export interface ProjectHeaderProps {
  currentProject: ProjectResponse | null;
  workflowName: string;
  workflowDirty: boolean;
}

export function ProjectHeader({ currentProject, workflowName, workflowDirty }: ProjectHeaderProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="rounded-[1.4rem] bg-ink px-4 py-2.5 text-stone-50">
        <p className="font-display text-lg leading-tight">SciStudio</p>
      </div>
      <div className="w-[200px] shrink-0">
        <p
          className="truncate font-display text-base leading-tight text-ink"
          title={currentProject?.name ?? undefined}
        >
          {currentProject?.name ?? "No project open"}
        </p>
        <p
          className="truncate text-xs text-stone-500"
          title={currentProject ? workflowName : undefined}
        >
          {currentProject ? (
            <>
              {workflowName}
              <span style={{ visibility: workflowDirty ? "visible" : "hidden" }}>{" *"}</span>
            </>
          ) : (
            "Open or create a project"
          )}
        </p>
      </div>
    </div>
  );
}

export function StatusPill({ connected, label }: { connected: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
        connected ? "bg-pine/15 text-pine" : "bg-stone-200 text-stone-500"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${connected ? "bg-pine" : "bg-stone-400"}`} />
      {label}
    </span>
  );
}
