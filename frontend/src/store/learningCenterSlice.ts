/**
 * ADR-053 Learning Center (#2057) — session *view* state.
 *
 * Spec §4.1: the frontend holds no judging logic and no step content. What is
 * kept here is only what the surface needs in order to render what the backend
 * last said — the catalogue, the active session, and whether the panel is open.
 * Every field is a copy of a backend answer or a fact about the panel itself;
 * none of it is consulted to decide whether a step is done. The actions below
 * are transport, not logic: each one calls a route and folds the response in.
 * Fetching from a slice follows `lineageSlice`, which does the same.
 *
 * Nothing here is persisted. FR-074 puts progress on the backend under
 * `~/.scistudio/` precisely so there is one copy: a browser-side mirror would
 * survive a backend that had moved on, and the desktop and web surfaces would
 * disagree. The removed `tutorialSlice` persisted four keys into
 * `scistudio-studio-ui`; they are gone with it (FR-001).
 *
 * Two edge cases in the spec drive the refresh design, and both come from state
 * living on the backend. A condition satisfied while the panel is closed is not
 * lost — `refreshLearningCenter` on open shows the current step. And a frontend
 * that disconnects mid-session missed nothing, because evaluation continued
 * without it — `refreshActiveTutorialSession` on reconnect picks the session up
 * where it now is. Neither path assumes a live stream is the only way in.
 */

import type { StateCreator } from "zustand";

import { ApiError } from "../lib/api/core";
import {
  learningCenterApi,
  TUTORIAL_SESSION_CONFLICT_STATUS,
  type TutorialCatalogueGroup,
  type TutorialCatalogueResponse,
  type TutorialSessionResponse,
  type TutorialStartRequest,
} from "../lib/api/learningCenter";

import type { AppStore, LearningCenterSlice } from "./types";

/** FR-084 — core is the group listed first and the only one driving behaviour. */
export const CORE_TUTORIAL_SOURCE_KIND = "core";

/**
 * FR-084 — groups in display order, core first.
 *
 * Ordering is settled here rather than in the component so the rule has one
 * home and a test can assert it directly. Within the non-core groups the
 * backend's order is kept, since it already sorts them.
 */
export function orderedTutorialGroups(
  catalogue: TutorialCatalogueResponse | null,
): TutorialCatalogueGroup[] {
  const groups = catalogueGroups(catalogue);
  const core = groups.filter((g) => g.source_kind === CORE_TUTORIAL_SOURCE_KIND);
  const rest = groups.filter((g) => g.source_kind !== CORE_TUTORIAL_SOURCE_KIND);
  return [...core, ...rest];
}

/**
 * The groups, or none.
 *
 * The catalogue is remote data, and these derivations run inside a render and a
 * mount effect — where a throw is not a caught error but a blank application.
 * A body that arrives without its `groups` array is treated as an empty
 * catalogue rather than allowed to take the window down with it.
 */
function catalogueGroups(catalogue: TutorialCatalogueResponse | null): TutorialCatalogueGroup[] {
  if (!catalogue || !Array.isArray(catalogue.groups)) return [];
  return catalogue.groups;
}

/** FR-080 — only the core group drives the unlock and the toolbar dot. */
export function coreTutorialGroup(
  catalogue: TutorialCatalogueResponse | null,
): TutorialCatalogueGroup | null {
  return (
    catalogueGroups(catalogue).find((g) => g.source_kind === CORE_TUTORIAL_SOURCE_KIND) ?? null
  );
}

/**
 * Whether the core group is finished.
 *
 * A group with no tutorials at all counts as complete: there is nothing left to
 * do, so there is nothing to point a user at.
 */
export function coreTutorialsComplete(catalogue: TutorialCatalogueResponse | null): boolean {
  const core = coreTutorialGroup(catalogue);
  if (!core) return true;
  return core.completed >= core.total;
}

/**
 * FR-083 — has the user any recorded tutorial progress?
 *
 * Derived from the catalogue the backend returned rather than tracked
 * separately, so "first launch" means what the backend's progress store says it
 * means. A tutorial that is merely listed is not progress; one that has been
 * started or finished is.
 */
export function hasRecordedTutorialProgress(catalogue: TutorialCatalogueResponse | null): boolean {
  if (!catalogue) return false;
  if (catalogue.active) return true;
  return catalogueGroups(catalogue).some(
    (group) =>
      group.completed > 0 ||
      (Array.isArray(group.tutorials) &&
        group.tutorials.some((t) => t.state === "in_progress" || t.state === "complete")),
  );
}

/**
 * FR-086 — the unfinished-work dot.
 *
 * Two conditions, both required: the core group is not fully complete, and the
 * user has dismissed the first-run landing. The second half matters because a
 * user still looking at the Learning Center does not need to be pointed back at
 * it. The dot clears on its own when the core group completes, and there is
 * deliberately no action that dismisses it permanently — an unfinished tutorial
 * the user has hidden forever is indistinguishable from a finished one.
 */
export function shouldShowUnfinishedTutorialDot(args: {
  catalogue: TutorialCatalogueResponse | null;
  firstRunLandingDismissed: boolean;
}): boolean {
  if (!args.firstRunLandingDismissed) return false;
  return !coreTutorialsComplete(args.catalogue);
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const createLearningCenterSlice: StateCreator<AppStore, [], [], LearningCenterSlice> = (
  set,
  get,
) => {
  /**
   * Fold a session response into view state.
   *
   * A session that has ended in error keeps its error visible rather than
   * vanishing: the spec's edge case for a driver that raises requires the user
   * be told which tutorial failed and why.
   */
  function adoptSession(session: TutorialSessionResponse | null): void {
    set({
      learningCenterSession: session,
      learningCenterError: session?.status === "error" ? (session.error ?? null) : null,
    });
  }

  return {
    learningCenterOpen: false,
    learningCenterCatalogue: null,
    learningCenterSession: null,
    learningCenterLoading: false,
    learningCenterError: null,
    learningCenterFirstRunDismissed: false,
    learningCenterStartConflict: null,

    openLearningCenter: () => set({ learningCenterOpen: true }),

    /*
     * Closing is also how the first-run landing is dismissed — FR-083 makes the
     * Learning Center the landing, so there is no separate dismiss gesture to
     * tell apart from closing it.
     */
    closeLearningCenter: () =>
      set({
        learningCenterOpen: false,
        learningCenterFirstRunDismissed: true,
        learningCenterStartConflict: null,
      }),

    setLearningCenterCatalogue: (catalogue) =>
      set({
        learningCenterCatalogue: catalogue,
        learningCenterSession: catalogue ? catalogue.active : null,
      }),

    setLearningCenterSession: (session) => adoptSession(session),

    setLearningCenterLoading: (learningCenterLoading) => set({ learningCenterLoading }),

    setLearningCenterError: (learningCenterError) => set({ learningCenterError }),

    clearLearningCenterStartConflict: () => set({ learningCenterStartConflict: null }),

    /** The catalogue carries the active session (§6.1.6), so one call refreshes both. */
    refreshLearningCenter: async () => {
      set({ learningCenterLoading: true, learningCenterError: null });
      try {
        const catalogue = await learningCenterApi.getTutorialCatalogue();
        set({
          learningCenterCatalogue: catalogue,
          learningCenterSession: catalogue.active,
        });
      } catch (error) {
        set({ learningCenterError: describe(error) });
      } finally {
        set({ learningCenterLoading: false });
      }
    },

    /** Reconnect path: the session alone, without redrawing the whole catalogue. */
    refreshActiveTutorialSession: async () => {
      try {
        adoptSession(await learningCenterApi.getActiveTutorialSession());
      } catch (error) {
        set({ learningCenterError: describe(error) });
      }
    },

    startTutorial: async (request: TutorialStartRequest) => {
      set({
        learningCenterLoading: true,
        learningCenterError: null,
        learningCenterStartConflict: null,
      });
      try {
        adoptSession(await learningCenterApi.startTutorialSession(request));
        // The entry's state and the group's count both moved.
        const catalogue = await learningCenterApi.getTutorialCatalogue();
        set({ learningCenterCatalogue: catalogue });
      } catch (error) {
        /*
         * One tutorial runs at a time. A 409 is not a failure to report as an
         * error string — it is the product telling the user something true, so
         * the request is held and the surface offers to leave the running one.
         */
        if (error instanceof ApiError && error.status === TUTORIAL_SESSION_CONFLICT_STATUS) {
          set({ learningCenterStartConflict: request });
        } else {
          set({ learningCenterError: describe(error) });
        }
      } finally {
        set({ learningCenterLoading: false });
      }
    },

    /** FR-053 — ask the backend to re-read state no mapped event reaches. */
    evaluateActiveTutorialStep: async () => {
      try {
        adoptSession(await learningCenterApi.evaluateActiveTutorialStep());
      } catch (error) {
        set({ learningCenterError: describe(error) });
      }
    },

    /** FR-012 — the reading step's continue button, the only such button. */
    continueActiveTutorialStep: async () => {
      try {
        adoptSession(await learningCenterApi.continueActiveTutorialStep());
      } catch (error) {
        set({ learningCenterError: describe(error) });
      }
    },

    /**
     * FR-052 — report a named user-interface event.
     *
     * The only completion path originating in the frontend. It is a no-op when
     * no tutorial is running, so a call site can report unconditionally without
     * having to know whether anyone is listening.
     */
    reportTutorialUiEvent: async (name: string) => {
      if (!get().learningCenterSession) return;
      try {
        adoptSession(await learningCenterApi.reportTutorialUiEvent(name));
      } catch (error) {
        set({ learningCenterError: describe(error) });
      }
    },

    /** FR-090 — leave at any step. The backend keeps the session for later. */
    leaveActiveTutorial: async () => {
      try {
        await learningCenterApi.leaveActiveTutorialSession();
        set({ learningCenterSession: null });
        const catalogue = await learningCenterApi.getTutorialCatalogue();
        set({ learningCenterCatalogue: catalogue });
      } catch (error) {
        set({ learningCenterError: describe(error) });
      }
    },

    /** FR-088 — returns the directories actually deleted, for the report back. */
    clearTutorialData: async () => {
      set({ learningCenterLoading: true, learningCenterError: null });
      try {
        const result = await learningCenterApi.clearTutorialData();
        const catalogue = await learningCenterApi.getTutorialCatalogue();
        set({ learningCenterCatalogue: catalogue, learningCenterSession: catalogue.active });
        return result.deleted_directories;
      } catch (error) {
        set({ learningCenterError: describe(error) });
        return [];
      } finally {
        set({ learningCenterLoading: false });
      }
    },
  };
};
