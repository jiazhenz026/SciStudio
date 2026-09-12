import type { StateCreator } from "zustand";

import type { AppStore, ProjectDialogState, ProjectSlice } from "./types";

const defaultDialog: ProjectDialogState = {
  mode: "new",
  name: "",
  description: "",
  path: "",
};

export const createProjectSlice: StateCreator<AppStore, [], [], ProjectSlice> = (set) => ({
  currentProject: null,
  recentProjects: [],
  projectDialogOpen: false,
  projectDialog: defaultDialog,
  setProjects: (projects) => set({ recentProjects: projects }),
  /**
   * #2362 — changing project discards the outgoing project's git history.
   *
   * `logCache` / `logLoading` / `logFailed` are keyed by branch name, and
   * `main` is the default branch in every repository, so the incoming project
   * read the outgoing one's commits as its own — with working Restore and Diff
   * buttons aimed at SHAs that do not exist in this repo. `logFailed` leaked
   * the other way: a branch whose load had failed (deleting the open project
   * makes every git call 409) stayed latched, and the new project's history was
   * then permanently stuck empty, because `loadLog` early-returns on it.
   *
   * The sibling fields `branches` and `status` were already patched per
   * component with a `currentProjectId` effect. Doing it here instead makes the
   * boundary structural, so a later git cache cannot quietly miss it.
   */
  setCurrentProject: (project) =>
    set((state) => {
      if (state.currentProject?.id === project?.id) return { currentProject: project };
      return {
        currentProject: project,
        logCache: {},
        logLoading: {},
        logFailed: {},
        branches: null,
        currentBranch: null,
        status: null,
      };
    }),
  openProjectDialog: (mode, partial) =>
    set({
      projectDialogOpen: true,
      projectDialog: {
        ...defaultDialog,
        ...partial,
        mode,
      },
    }),
  closeProjectDialog: () => set({ projectDialogOpen: false }),
  updateProjectDialog: (patch) =>
    set((state) => ({
      projectDialog: {
        ...state.projectDialog,
        ...patch,
      },
    })),
});
