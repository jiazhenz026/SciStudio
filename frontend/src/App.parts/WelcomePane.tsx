import type { ProjectResponse } from "../types/api";

import { WelcomeScreen } from "../components/WelcomeScreen";

interface WelcomePaneProps {
  recentProjects: ProjectResponse[];
  tutorialPromptVisible: boolean;
  onDeleteProject: (projectId: string) => void;
  onNewProject: () => void;
  onOpenProject: () => void;
  onOpenRecent: (projectId: string) => void;
  onStartTutorial: () => void;
  onDismissTutorial: () => void;
  onSuppressTutorial: () => void;
}

export function WelcomePane({
  recentProjects,
  tutorialPromptVisible,
  onDeleteProject,
  onNewProject,
  onOpenProject,
  onOpenRecent,
  onStartTutorial,
  onDismissTutorial,
  onSuppressTutorial,
}: WelcomePaneProps) {
  return (
    <div className="min-h-0 flex-1">
      <WelcomeScreen
        onDeleteProject={onDeleteProject}
        onNewProject={onNewProject}
        onOpenProject={onOpenProject}
        onOpenRecent={onOpenRecent}
        recentProjects={recentProjects}
        tutorialPromptVisible={tutorialPromptVisible}
        onStartTutorial={onStartTutorial}
        onDismissTutorial={onDismissTutorial}
        onSuppressTutorial={onSuppressTutorial}
      />
    </div>
  );
}
