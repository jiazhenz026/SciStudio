import type {
  ProjectDialogState,
  VersionConflictState,
  WorkflowConflictResolution,
} from "../store/types";
import type { ProjectResponse } from "../types/api";

import { ProjectDialog } from "../components/ProjectDialog";
import { PromptDialog, type PromptRequest } from "../components/PromptDialog";
import { UserLibraryDialogs } from "../components/promotion/UserLibraryDialogs";
import { WorkflowConflictDialog } from "../components/WorkflowConflictDialog";

interface AppDialogsProps {
  projectDialog: ProjectDialogState;
  projectDialogOpen: boolean;
  /** #2019: a project create/open is in flight — block a second submit. */
  busy: boolean;
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
  busy,
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
        busy={busy}
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

      {/* ADR-053 §6 / §8 — the promotion collision + cascade prompts (FR-018,
          FR-023), the new-file destination choice (FR-029), and the inline
          success confirmation (FR-020). Mounted once and driven through
          `dialogChannel`, so every entry point asks the same questions. */}
      <UserLibraryDialogs />
    </>
  );
}
