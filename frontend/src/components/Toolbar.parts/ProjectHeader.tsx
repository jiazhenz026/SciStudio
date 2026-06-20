/**
 * Logo + active-project label inside the Toolbar. Extracted in #1413.
 */
import type { ConnectionStatus } from "../../hooks/connectionState";
import type { ProjectResponse } from "../../types/api";

export interface ProjectHeaderProps {
  currentProject: ProjectResponse | null;
  workflowName: string;
  workflowDirty: boolean;
}

export function ProjectHeader({ currentProject, workflowName, workflowDirty }: ProjectHeaderProps) {
  return (
    <div
      className="flex min-w-0 shrink-0 items-center gap-2 xl:gap-3"
      data-testid="toolbar-project-header"
    >
      <div className="shrink-0 rounded-[1.4rem] bg-ink px-3 py-2 text-stone-50 xl:px-4 xl:py-2.5">
        <p className="font-display text-lg leading-tight">SciStudio</p>
      </div>
      <div
        className="hidden min-w-0 shrink xl:block xl:max-w-[80px] 2xl:max-w-[100px]"
        data-testid="toolbar-project-meta"
      >
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

/**
 * Connection indicator pill.
 *
 * #177: when `status` is supplied it drives a three-way visual:
 * connected, reconnecting/connecting, or disconnected. When `status` is
 * absent it falls back to the boolean `connected` so older call sites keep
 * working.
 */
export function StatusPill({
  connected,
  status,
  label,
}: {
  connected: boolean;
  status?: ConnectionStatus;
  label: string;
}) {
  const effective: ConnectionStatus = status ?? (connected ? "connected" : "disconnected");
  const isReconnecting = effective === "reconnecting" || effective === "connecting";

  let pillClass = "bg-stone-200 text-stone-500";
  let dotClass = "bg-stone-400";
  let title = `${label}: disconnected`;
  if (effective === "connected") {
    pillClass = "bg-pine/15 text-pine";
    dotClass = "bg-pine";
    title = `${label}: connected`;
  } else if (isReconnecting) {
    pillClass = "bg-amber-100 text-amber-700";
    dotClass = "bg-amber-500 animate-pulse";
    title = `${label}: ${effective === "connecting" ? "connecting" : "reconnecting"}...`;
  }

  return (
    <span
      title={title}
      data-status={effective}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${pillClass}`}
    >
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      <span className="hidden xl:inline">{label}</span>
    </span>
  );
}
