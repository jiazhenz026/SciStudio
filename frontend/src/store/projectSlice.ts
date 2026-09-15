import type { StateCreator } from "zustand";

import type { AppStore, ProjectDialogState, ProjectSlice } from "./types";

const defaultDialog: ProjectDialogState = {
  mode: "new",
  name: "",
  description: "",
  path: "",
};

export const createProjectSlice: StateCreator<AppStore, [], [], ProjectSlice> = (set, get) => ({
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
   *
   * #2395 — the same boundary covers the plot result and the Lineage tab.
   * `plotPreviewTarget` names its node only by `(workflow_id, node_id)`, which
   * the next project can repeat (`main`, `load_one`), so it rendered the
   * previous project's plot. Lineage selection and cached run details survived
   * until LineageTab happened to mount, and `clearLineage` also drops any
   * `/api/runs` response still in flight for the outgoing project.
   */
  setCurrentProject: (project) => {
    if (get().currentProject?.id === project?.id) {
      set({ currentProject: project });
      return;
    }
    get().clearLineage();
    set({
      currentProject: project,
      logCache: {},
      logLoading: {},
      logFailed: {},
      branches: null,
      currentBranch: null,
      status: null,
      plotPreviewTarget: null,
    });
  },
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
