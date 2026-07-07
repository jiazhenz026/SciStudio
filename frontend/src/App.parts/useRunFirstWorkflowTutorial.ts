import { useCallback } from "react";

import { api } from "../lib/api";
import { useAppStore } from "../store";
import { instanceFromBootstrap } from "../tutorials/runFirstWorkflow/content";

interface UseRunFirstWorkflowTutorialArgs {
  openProject: (projectId: string) => Promise<void>;
  setBusy: (busy: boolean) => void;
  setLastError: (message: string | null) => void;
}

export function useRunFirstWorkflowTutorial({
  openProject,
  setBusy,
  setLastError,
}: UseRunFirstWorkflowTutorialArgs) {
  const tutorialPrefs = useAppStore((state) => state.runFirstWorkflowTutorialPrefs);
  const startRunFirstWorkflowTutorial = useAppStore((state) => state.startRunFirstWorkflowTutorial);
  const dismissRunFirstWorkflowTutorialPrompt = useAppStore(
    (state) => state.dismissRunFirstWorkflowTutorialPrompt,
  );
  const suppressRunFirstWorkflowTutorialPrompt = useAppStore(
    (state) => state.suppressRunFirstWorkflowTutorialPrompt,
  );

  const tutorialPromptVisible =
    !tutorialPrefs.completedAt && !tutorialPrefs.dismissedAt && !tutorialPrefs.suppressAutoStart;

  const startTutorial = useCallback(async () => {
    setBusy(true);
    setLastError(null);
    try {
      const bootstrap = await api.bootstrapRunFirstWorkflowTutorial();
      startRunFirstWorkflowTutorial(instanceFromBootstrap(bootstrap));
      await openProject(bootstrap.project.id);
    } catch (error) {
      setLastError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [openProject, setBusy, setLastError, startRunFirstWorkflowTutorial]);

  return {
    tutorialPromptVisible,
    startTutorial,
    dismissRunFirstWorkflowTutorialPrompt,
    suppressRunFirstWorkflowTutorialPrompt,
  };
}
