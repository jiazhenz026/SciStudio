import type {
  ProjectDialogState,
  VersionConflictState,
  WorkflowConflictResolution,
} from "../store/types";
import type { ProjectResponse } from "../types/api";

import { ProjectDialog } from "../components/ProjectDialog";
import { PromptDialog, type PromptRequest } from "../components/PromptDialog";
import { WorkflowConflictDialog } from "../components/WorkflowConflictDialog";

interface AppDialogsProps {
  projectDialog: ProjectDialogState;
  projectDialogOpen: boolean;
  promptRequest: PromptRequest | null;
  recentProjects: ProjectResponse[];
  workflowConflict: VersionConflictState | null;
  onProjectDialogChange: (patch: Partial<ProjectDialogState>) => void;
  onProjectDialogClose: () => void;
  onProjectDialogSubmit: () => void;
  onDeleteProject: (projectId: string) => void;
  onOpenRecent: (projectId: string) => void;
  onPromptClose: () => void;
  onResolveWorkflowConflict: (resolution: WorkflowConflictResolution) => void;
}

export function AppDialogs({
  projectDialog,
  projectDialogOpen,
  promptRequest,
  recentProjects,
  workflowConflict,
  onProjectDialogChange,
  onProjectDialogClose,
  onProjectDialogSubmit,
  onDeleteProject,
  onOpenRecent,
  onPromptClose,
  onResolveWorkflowConflict,
}: AppDialogsProps) {
  return (
    <>
      <ProjectDialog
        description={projectDialog.description}
        mode={projectDialog.mode}
        name={projectDialog.name}
        onChange={onProjectDialogChange}
        onClose={onProjectDialogClose}
        onDeleteProject={onDeleteProject}
        onOpenRecent={onOpenRecent}
        onSubmit={onProjectDialogSubmit}
        open={projectDialogOpen}
        path={projectDialog.path}
        recentProjects={recentProjects}
      />

      <PromptDialog request={promptRequest} onClose={onPromptClose} />

      <WorkflowConflictDialog conflict={workflowConflict} onResolve={onResolveWorkflowConflict} />
    </>
  );
}
