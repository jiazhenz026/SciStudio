import type { ProjectResponse } from "../types/api";

interface WelcomeScreenProps {
  recentProjects: ProjectResponse[];
  onNewProject: () => void;
  onOpenProject: () => void;
  onOpenRecent: (projectId: string) => void;
  onDeleteProject?: (projectId: string) => void;
  tutorialPromptVisible?: boolean;
  onStartTutorial?: () => void;
  onDismissTutorial?: () => void;
  onSuppressTutorial?: () => void;
}

export function WelcomeScreen({
  recentProjects,
  onNewProject,
  onOpenProject,
  onOpenRecent,
  onDeleteProject,
  tutorialPromptVisible = false,
  onStartTutorial,
  onDismissTutorial,
  onSuppressTutorial,
}: WelcomeScreenProps) {
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
    <div className="flex h-full items-center justify-center overflow-auto p-6">
      <div className="w-full max-w-4xl rounded-[2.5rem] border border-stone-200 bg-[radial-gradient(circle_at_top_left,_rgba(240,106,68,0.2),_transparent_35%),linear-gradient(135deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-8 shadow-panel">
        <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="flex h-full flex-col">
            <div className="my-auto">
              <h1 className="max-w-xl font-display text-7xl leading-tight text-ink">SciStudio</h1>
              <p className="mt-4 max-w-2xl text-lg leading-8 text-stone-600">
                Every tool. Every format. One workflow.
              </p>
              {tutorialPromptVisible ? (
                <div className="mt-6 rounded-lg border border-ember/30 bg-white/85 p-4 shadow-sm">
                  <p className="text-[0.65rem] uppercase tracking-[0.24em] text-ember">Tutorial</p>
                  <h2 className="mt-1 text-base font-semibold text-ink">
                    Run Your First SciStudio Workflow
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Create a sample project, normalize fluorescence data, build a workflow, create a
                    plot card, and review history.
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      className="rounded-full bg-ink px-4 py-2 text-xs font-medium text-white transition hover:bg-pine"
                      onClick={onStartTutorial}
                      type="button"
                    >
                      Start tutorial
                    </button>
                    <button
                      className="rounded-full border border-stone-300 bg-white px-3 py-2 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                      onClick={onDismissTutorial}
                      type="button"
                    >
                      Not now
                    </button>
                    <button
                      className="rounded-full px-3 py-2 text-xs font-medium text-stone-500 transition hover:bg-stone-100 hover:text-ink"
                      onClick={onSuppressTutorial}
                      type="button"
                    >
                      Don&apos;t show again
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-3 pt-8">
              <button
                className="rounded-full bg-ink px-6 py-3 text-sm font-medium text-stone-50 transition hover:bg-pine"
                onClick={onNewProject}
                type="button"
              >
                New Project
              </button>
              <button
                className="rounded-full border border-stone-300 bg-white px-6 py-3 text-sm font-medium text-ink transition hover:border-ember hover:text-ember"
                onClick={onOpenProject}
                type="button"
              >
                Open Project
              </button>
            </div>
          </div>

          <div className="rounded-[2rem] border border-stone-200 bg-white/80 p-5">
            <p className="text-xs uppercase tracking-[0.3em] text-stone-500">Recent Workspaces</p>
            <div className="mt-4 flex max-h-80 flex-col gap-3 overflow-y-auto">
              {recentProjects.length ? (
                recentProjects.map((project) => (
                  <button
                    className="flex items-center justify-between rounded-[1.5rem] border border-stone-200 px-4 py-4 text-left transition hover:border-pine hover:bg-pine/5"
                    key={project.id}
                    onClick={() => onOpenRecent(project.id)}
                    type="button"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-ink">{project.name}</span>
                      <span className="mt-1 block max-w-[300px] truncate text-xs text-stone-500">
                        {project.path}
                      </span>
                    </span>
                    {onDeleteProject ? (
                      <span
                        className="ml-2 shrink-0 rounded-full p-1 text-stone-400 transition hover:bg-red-50 hover:text-red-600"
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
                  </button>
                ))
              ) : (
                <p className="text-sm text-stone-500">No recent projects yet.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
