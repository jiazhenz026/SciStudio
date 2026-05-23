/**
 * Recent-projects card inside ProjectDialog. Extracted in #1413.
 */
import type { ProjectResponse } from "../../types/api";

export interface RecentProjectsListProps {
  recentProjects: ProjectResponse[];
  onOpenRecent: (projectIdOrPath: string) => void;
  onDeleteProject?: (projectId: string) => void;
  onDeleteClick: (event: React.MouseEvent, projectId: string, projectName: string) => void;
}

function DeleteIcon() {
  return (
    <svg className="size-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path
        d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function RecentProjectRow({
  project,
  onOpenRecent,
  onDeleteProject,
  onDeleteClick,
}: {
  project: ProjectResponse;
  onOpenRecent: (projectIdOrPath: string) => void;
  onDeleteProject?: (projectId: string) => void;
  onDeleteClick: (event: React.MouseEvent, projectId: string, projectName: string) => void;
}) {
  return (
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
            onClick={(event) => onDeleteClick(event, project.id, project.name)}
            onKeyDown={() => {}}
            role="button"
            tabIndex={0}
            title="Delete project"
          >
            <DeleteIcon />
          </span>
        ) : null}
      </span>
    </button>
  );
}

export function RecentProjectsList({
  recentProjects,
  onOpenRecent,
  onDeleteProject,
  onDeleteClick,
}: RecentProjectsListProps) {
  return (
    <div className="mt-6 rounded-[1.5rem] border border-stone-200 bg-white/80 p-4">
      <p className="text-xs uppercase tracking-[0.3em] text-stone-500">Recent projects</p>
      <div className="mt-3 flex max-h-64 flex-col gap-2 overflow-y-auto">
        {recentProjects.length ? (
          recentProjects.map((project) => (
            <RecentProjectRow
              key={project.id}
              project={project}
              onOpenRecent={onOpenRecent}
              onDeleteProject={onDeleteProject}
              onDeleteClick={onDeleteClick}
            />
          ))
        ) : (
          <p className="text-sm text-stone-500">
            No project history yet. Create one to get started.
          </p>
        )}
      </div>
    </div>
  );
}
