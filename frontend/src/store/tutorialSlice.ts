import type { StateCreator } from "zustand";

import type { AppStore, TutorialSlice } from "./types";

export const createTutorialSlice: StateCreator<AppStore, [], [], TutorialSlice> = (set) => ({
  runFirstWorkflowTutorialActive: false,
  runFirstWorkflowTutorialStep: "inspect-data",
  runFirstWorkflowTutorialInstance: null,
  runFirstWorkflowTutorialPrefs: {},
  startRunFirstWorkflowTutorial: (instance) =>
    set({
      runFirstWorkflowTutorialActive: true,
      runFirstWorkflowTutorialStep: "inspect-data",
      runFirstWorkflowTutorialInstance: instance,
      runFirstWorkflowTutorialPrefs: {},
    }),
  setRunFirstWorkflowTutorialStep: (step) => set({ runFirstWorkflowTutorialStep: step }),
  exitRunFirstWorkflowTutorial: () => set({ runFirstWorkflowTutorialActive: false }),
  completeRunFirstWorkflowTutorial: () =>
    set({
      runFirstWorkflowTutorialActive: false,
      runFirstWorkflowTutorialStep: "finish",
      runFirstWorkflowTutorialPrefs: { completedAt: new Date().toISOString() },
    }),
  dismissRunFirstWorkflowTutorialPrompt: () =>
    set((state) => ({
      runFirstWorkflowTutorialPrefs: {
        ...state.runFirstWorkflowTutorialPrefs,
        dismissedAt: new Date().toISOString(),
      },
    })),
  suppressRunFirstWorkflowTutorialPrompt: () =>
    set((state) => ({
      runFirstWorkflowTutorialPrefs: {
        ...state.runFirstWorkflowTutorialPrefs,
        suppressAutoStart: true,
      },
    })),
});
