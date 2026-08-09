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
   * `App`'s own left-panel state setter.
   *
   * Passed in rather than read from the store because `leftTab` is React state
   * local to `App`; a step routing to the block palette has to go through the
   * component that owns it.
   */
  setLeftTab: (tab: LeftTab) => void;
}

export function useLearningCenter({ wsConnected, setLeftTab }: UseLearningCenterArgs): void {
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
   * The ref only stops the same completion asking twice; it is not a record of
   * whether the offer has been shown. That question has one owner, and it is
   * the backend: `GET /unlock` answers it, and a second copy here would be the
   * thing that makes a once-only offer appear twice.
   */
  const checkWorkImportOffer = useAppStore((state) => state.checkWorkImportOffer);
  const completedTutorialKey = useAppStore((state) => {
    const active = state.learningCenterSession;
    if (!active || active.status !== "complete") return null;
    return `${active.source_kind}:${active.source_id}:${active.tutorial_id}`;
  });
  const lastCompletionAsked = useRef<string | null>(null);

  useEffect(() => {
    if (!completedTutorialKey) return;
    if (lastCompletionAsked.current === completedTutorialKey) return;
    lastCompletionAsked.current = completedTutorialKey;
    void checkWorkImportOffer();
  }, [completedTutorialKey, checkWorkImportOffer]);

  useEffect(() => {
    if (!tutorialStepKey || !tutorialStepRoute) return;
    applyStepRoute(tutorialStepRoute, { openBottomTab, setLeftTab });
    // `tutorialStepRoute` is a property of the step `tutorialStepKey` names, so
    // the key alone decides when this runs. Adding the route or the two setters
    // would re-route on identity changes that are not a new step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tutorialStepKey]);
}
