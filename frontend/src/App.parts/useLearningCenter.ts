/**
 * ADR-053 Learning Center (#2057) — the four effects that keep the Learning
 * Center in step with the backend, extracted from `App.tsx`.
 *
 * They live together because they answer one question in four places: what does
 * the backend currently say, and what should the product do about it. Nothing
 * here decides whether a step is satisfied — spec §4.1 puts that on the backend
 * — and nothing here holds step content.
 */

import { useEffect, useRef } from "react";

import { applyStepRoute } from "../components/LearningCenter.parts/targets";
import { useAppStore } from "../store";
import { hasRecordedTutorialProgress } from "../store/learningCenterSlice";

import type { LeftTab } from "./ProjectWorkspace";

interface UseLearningCenterArgs {
  /** Drives the reconnect refetch below. */
  wsConnected: boolean;
  /**
   * `App`'s project opener.
   *
   * A tutorial that declares `bootstrap` gets a project created for it on the
   * backend (FR-062), and the session names it. Opening it is the frontend's
   * job: the backend has no way to move the window.
   */
  openProject: (projectIdOrPath: string) => Promise<void> | void;
  /**
   * `App`'s own left-panel state setter.
   *
   * Passed in rather than read from the store because `leftTab` is React state
   * local to `App`; a step routing to the block palette has to go through the
   * component that owns it.
   */
  setLeftTab: (tab: LeftTab) => void;
  /**
   * `App`'s project closer, for the end of a tutorial.
   *
   * A finished tutorial leaves its project open, and a tutorial project looks
   * like any other workspace: the reader carries on working in a directory the
   * product created for a lesson, which restarting the tutorial deletes
   * (FR-066). Closing it is the frontend's job for the same reason opening it
   * is — the backend cannot move the window.
   */
  closeProject: () => void;
}

export function useLearningCenter({
  wsConnected,
  setLeftTab,
  openProject,
  closeProject,
}: UseLearningCenterArgs): void {
  const refreshLearningCenter = useAppStore((state) => state.refreshLearningCenter);
  const refreshActiveTutorialSession = useAppStore((state) => state.refreshActiveTutorialSession);
  const openLearningCenter = useAppStore((state) => state.openLearningCenter);
  const openBottomTab = useAppStore((state) => state.openBottomTab);
  const learningCenterCatalogue = useAppStore((state) => state.learningCenterCatalogue);
  const learningCenterFirstRunDismissed = useAppStore(
    (state) => state.learningCenterFirstRunDismissed,
  );

  /*
   * The catalogue is fetched once at start-up because two surfaces need it
   * before the panel is ever opened: the toolbar dot (FR-086) and the decision
   * of whether this is a first run (FR-083).
   */
  useEffect(() => {
    void refreshLearningCenter();
  }, [refreshLearningCenter]);

  /*
   * FR-083 — on first launch with no recorded progress, the Learning Center is
   * what the user sees. "No recorded progress" is read off the catalogue the
   * backend returned rather than tracked here, so first-run means what the
   * backend's progress store says it means (FR-074).
   */
  const firstRunLandingShown = useRef(false);
  useEffect(() => {
    if (firstRunLandingShown.current) return;
    if (!learningCenterCatalogue) return;
    if (learningCenterFirstRunDismissed) return;
    if (hasRecordedTutorialProgress(learningCenterCatalogue)) return;
    firstRunLandingShown.current = true;
    openLearningCenter();
  }, [learningCenterCatalogue, learningCenterFirstRunDismissed, openLearningCenter]);

  /*
   * Open the project the active session names.
   *
   * FR-062 gives a tutorial that declares `bootstrap` a project of its own, and
   * FR-063 registers it, but nothing on the backend can move the user's window
   * — so without this the session starts, the step renders, and the user is
   * looking at whatever project they had open, or at the welcome pane with no
   * project at all. The tutorial reads as stuck while being entirely healthy.
   *
   * Keyed on the session's project rather than on the start call, so it covers
   * resuming as well: User Story 2 requires reopening a half-finished tutorial
   * to put the user back on the same step *in the same project*, which is the
   * same move made from a different direction.
   *
   * The ref guards against re-entry while the open is in flight, since opening
   * a project refreshes the project list and the block catalogue and would
   * otherwise re-trigger this effect before `currentProjectId` has caught up.
   */
  /*
   * Only a live session moves the window. The backend keeps an ended session
   * as the active record with status `complete` or `error`, so the session
   * adopted at start-up can be one that finished long ago (#2079) — opening
   * its project then would resurrect a workspace the lesson is done with.
   */
  const tutorialProjectId = useAppStore((state) =>
    state.learningCenterSession?.status === "active"
      ? (state.learningCenterSession.project_id ?? null)
      : null,
  );
  const currentProjectId = useAppStore((state) => state.currentProject?.id ?? null);
  const openingTutorialProject = useRef<string | null>(null);

  useEffect(() => {
    if (!tutorialProjectId) {
      openingTutorialProject.current = null;
      return;
    }
    if (tutorialProjectId === currentProjectId) return;
    if (openingTutorialProject.current === tutorialProjectId) return;
    openingTutorialProject.current = tutorialProjectId;
    void openProject(tutorialProjectId);
  }, [tutorialProjectId, currentProjectId, openProject]);

  /*
   * Ask again whenever the open project changes.
   *
   * A session is bound to its own project, and the backend answers "no session"
   * while some other project is open — the tutorial is dormant, not over. That
   * answer is only useful if it is asked for: without this, closing the tutorial
   * project left the last session in this store, so the step card stayed over
   * the user's own project and a step's `prefill` went on seeding dialogs there.
   * Reopening the tutorial project asks again and the session comes back, which
   * is the same request serving the resume.
   */
  useEffect(() => {
    void refreshActiveTutorialSession();
  }, [currentProjectId, refreshActiveTutorialSession]);

  /*
   * Spec edge case — the frontend disconnects mid-session. Evaluation carried
   * on without it, so on reconnect the session is fetched and the current step
   * rendered. Nothing is replayed: the backend's answer is the whole truth, and
   * this is why the design does not depend on a live stream being the only way
   * a step advances.
   */
  const wasWsConnected = useRef(wsConnected);
  useEffect(() => {
    if (wsConnected && !wasWsConnected.current) {
      void refreshActiveTutorialSession();
    }
    wasWsConnected.current = wsConnected;
  }, [wsConnected, refreshActiveTutorialSession]);

  /*
   * Take the user to the surface the step names, on step entry.
   *
   * Keyed on the step's identity rather than on the session object, so it fires
   * once when a step is entered and not again on every unrelated re-render — a
   * step that reopened the Plots tab every time the store changed would be
   * fighting a user who had deliberately navigated away mid-step.
   */
  const tutorialStepRoute = useAppStore(
    (state) => state.learningCenterSession?.step?.route_to ?? null,
  );
  const tutorialStepKey = useAppStore((state) => {
    const active = state.learningCenterSession;
    if (!active?.step) return null;
    return `${active.source_kind}:${active.source_id}:${active.tutorial_id}:${active.step.id}`;
  });

  /*
   * FR-079 — when a tutorial finishes, ask whether the product should now
   * volunteer the work-import offer.
   *
   * A completion is only news when this app run watched the tutorial run.
   * The backend keeps an ended session as the active record with status
   * `complete` rather than erasing it (see `tutorials/session.py`), so every
   * launch adopts the last finished tutorial as a session that is complete
   * already. Treating that record as a fresh finish is the #2079 bug: the
   * Learning Center opened — and the open project closed — on every restart.
   * The reaction below therefore fires only for a completion this app run
   * witnessed (the session was seen in a non-complete state first), or for one
   * that is not the session adopted already-complete at start-up, which keeps
   * a finish that happened while the frontend was disconnected on the reconnect
   * path.
   *
   * The `lastCompletionAsked` ref only stops the same completion asking twice;
   * it is not a record of whether the offer has been shown. That question has
   * one owner, and it is the backend: `GET /unlock` answers it, and a second
   * copy here would be the thing that makes a once-only offer appear twice.
   */
  const checkWorkImportOffer = useAppStore((state) => state.checkWorkImportOffer);
  const tutorialSessionKey = useAppStore((state) => {
    const active = state.learningCenterSession;
    if (!active) return null;
    return `${active.source_kind}:${active.source_id}:${active.tutorial_id}`;
  });
  const tutorialSessionComplete = useAppStore(
    (state) => state.learningCenterSession?.status === "complete",
  );
  const seenRunningTutorial = useRef<string | null>(null);
  const startupCompletedTutorial = useRef<string | null | undefined>(undefined);
  const lastCompletionAsked = useRef<string | null>(null);

  /*
   * Record the session the first catalogue load arrives with. Declared before
   * the completion effect so that, when one store update carries both the
   * catalogue and its already-complete active session, this runs first.
   */
  useEffect(() => {
    if (startupCompletedTutorial.current !== undefined) return;
    if (!learningCenterCatalogue) return;
    const active = learningCenterCatalogue.active;
    startupCompletedTutorial.current =
      active && active.status === "complete"
        ? `${active.source_kind}:${active.source_id}:${active.tutorial_id}`
        : null;
  }, [learningCenterCatalogue]);

  useEffect(() => {
    if (!tutorialSessionKey) return;
    if (!tutorialSessionComplete) {
      seenRunningTutorial.current = tutorialSessionKey;
      return;
    }
    if (lastCompletionAsked.current === tutorialSessionKey) return;
    const witnessed = seenRunningTutorial.current === tutorialSessionKey;
    const staleFromStartUp = startupCompletedTutorial.current === tutorialSessionKey;
    if (!witnessed && staleFromStartUp) return;
    lastCompletionAsked.current = tutorialSessionKey;
    void checkWorkImportOffer();
    /*
     * Finishing lands in the Learning Center rather than in a card saying so.
     *
     * "Tutorial complete." in the corner is a dead end: it reports the outcome
     * and leaves the reader looking at a workspace with nothing to do next.
     * The catalogue is where the next tutorial is, so finishing one opens it.
     */
    openLearningCenter();
    // ...and out of the tutorial's project, before it looks like somewhere to
    // keep working. See `closeProject` above.
    closeProject();
  }, [
    tutorialSessionKey,
    tutorialSessionComplete,
    checkWorkImportOffer,
    openLearningCenter,
    closeProject,
  ]);

  useEffect(() => {
    if (!tutorialStepKey || !tutorialStepRoute) return;
    applyStepRoute(tutorialStepRoute, { openBottomTab, setLeftTab });
    // `tutorialStepRoute` is a property of the step `tutorialStepKey` names, so
    // the key alone decides when this runs. Adding the route or the two setters
    // would re-route on identity changes that are not a new step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tutorialStepKey]);
}
