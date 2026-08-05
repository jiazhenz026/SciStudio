import type { StateCreator } from "zustand";

import type { AppStore, TutorialSlice } from "./types";

export const createTutorialSlice: StateCreator<AppStore, [], [], TutorialSlice> = (set) => ({
  runFirstWorkflowTutorialActive: false,
  runFirstWorkflowTutorialStep: "inspect-data",
  runFirstWorkflowTutorialInstance: null,
  runFirstWorkflowTutorialPrefs: {},
  // #1986: prefs are deliberately left alone here. Resetting them meant that
  // starting the tutorial erased an earlier "Don't show again" or completion,
  // so the welcome prompt came back the moment the user closed the panel.
  startRunFirstWorkflowTutorial: (instance) =>
    set({
      runFirstWorkflowTutorialActive: true,
      runFirstWorkflowTutorialStep: "inspect-data",
      runFirstWorkflowTutorialInstance: instance,
    }),
  setRunFirstWorkflowTutorialStep: (step) => set({ runFirstWorkflowTutorialStep: step }),
  exitRunFirstWorkflowTutorial: () => set({ runFirstWorkflowTutorialActive: false }),
  completeRunFirstWorkflowTutorial: () =>
    set((state) => ({
      runFirstWorkflowTutorialActive: false,
      runFirstWorkflowTutorialStep: "finish",
      runFirstWorkflowTutorialPrefs: {
        ...state.runFirstWorkflowTutorialPrefs,
        completedAt: new Date().toISOString(),
      },
    })),
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
