import type { ProjectResponse } from "../types/api";

import { WelcomeScreen } from "../components/WelcomeScreen";

/**
 * ADR-053 FR-001 / FR-083 — the four tutorial-prompt props are gone.
 *
 * The first-run offer is no longer a card this pane passes through; the
 * Learning Center is what a user with no recorded progress sees, and it is
 * mounted by `App.tsx` above whatever this pane renders.
 */
interface WelcomePaneProps {
  recentProjects: ProjectResponse[];
  onDeleteProject: (projectId: string) => void;
  onNewProject: () => void;
  onOpenProject: () => void;
  onOpenRecent: (projectId: string) => void;
}

export function WelcomePane({
  recentProjects,
  onDeleteProject,
  onNewProject,
  onOpenProject,
  onOpenRecent,
}: WelcomePaneProps) {
  return (
    <div className="min-h-0 flex-1">
      <WelcomeScreen
        onDeleteProject={onDeleteProject}
        onNewProject={onNewProject}
        onOpenProject={onOpenProject}
        onOpenRecent={onOpenRecent}
        recentProjects={recentProjects}
      />
    </div>
  );
}
