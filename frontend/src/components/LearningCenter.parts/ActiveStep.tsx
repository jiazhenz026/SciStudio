/**
 * ADR-053 Learning Center (#2057, #2136) — the active step surface (FR-089, FR-090).
 *
 * FR-089 requires the active step be shown without occluding the element it
 * refers to. A step card satisfied that by standing beside its target
 * (`placeCard`); the dialogue surface satisfies it by being small enough to
 * stand in a corner and taking whichever corner the lit target is not in
 * (`placeDialogue`). Either way the target is ringed where it sits
 * (`TargetHighlight`), and a step pointing at nothing rings nothing.
 *
 * It renders the step view the backend returned and nothing else. There is no
 * step content here and no judging: spec §4.1 puts both on the backend, and
 * FR-002 removed the five frontend predicates that used to do the judging by
 * reading the frontend's copy of the workflow.
 *
 * **Some steps advance on their own, and the step says which** (FR-054c). The
 * backend re-judges on the engine events of FR-050 and reports whether the
 * current step's condition holds; a step that declared `auto_advance` moves on
 * the moment it does, and every other step lights Continue and waits.
 *
 * Automatic advance was the original design, was reversed on 2026-08-10 because
 * a step completing while its text was still being read replaced that text with
 * the next step's and left no way back to it, and was restored per step on
 * 2026-08-23 (#2136). Both halves of that objection have moved: there is a back
 * control now (#2138), and the reading is delivered a beat at a time, so the
 * advance waits until the whole step has been shown. What is left is a
 * judgment only the author can make — whether the reader is meant to *look* at
 * what they just did — and it is theirs to declare.
 *
 * **Beats advance, steps do not** (#2135, #2136). A step's `say` is the ordered
 * beats its author wrote it in, and the reader walks them one click at a time.
 * That click is not Continue and never advances the step: Continue stays dark
 * until the last beat is on screen, so a reader cannot leave a step whose text
 * they have not been shown. Which beat they are on is frontend state by
 * FR-011d, so leaving and returning re-enters the step at its first beat —
 * their context is gone either way, and re-reading is the correct recovery.
 *
 * "Check again" is FR-053: it covers state no mapped event reaches, such as a
 * data file whose extension is outside the `file.changed` allowlist.
 */

import { useEffect, useState } from "react";

import { useAppStore } from "../../store";

import { DialogueSurface } from "./DialogueSurface";
import { FinishChoice } from "./FinishChoice";
import { StepControls } from "./StepControls";
import { StepHeading } from "./StepHeading";
import { TutorialProblemBanner } from "./TutorialProblemBanner";
import { TargetHighlight } from "./TargetHighlight";
import { MIO_NAME, moodAt } from "./mio";
import { placeCard } from "./placeCard";
import { STAGE_TARGET, placeDialogue, stageBox } from "./placeDialogue";
import { advancesItself, canContinue, finishing, needsAction } from "./stepFlow";
import { useHighlightRect } from "./useHighlightRect";

function useViewport() {
  const [viewport, setViewport] = useState(() => ({
    width: typeof window === "undefined" ? 1280 : window.innerWidth,
    height: typeof window === "undefined" ? 800 : window.innerHeight,
  }));

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onResize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return viewport;
}

export function ActiveStep() {
  const session = useAppStore((state) => state.learningCenterSession);
  const learningCenterOpen = useAppStore((state) => state.learningCenterOpen);
  const openLearningCenter = useAppStore((state) => state.openLearningCenter);
  const evaluateStep = useAppStore((state) => state.evaluateActiveTutorialStep);
  const continueStep = useAppStore((state) => state.continueActiveTutorialStep);
  const backStep = useAppStore((state) => state.backActiveTutorialStep);
  const triggerStep = useAppStore((state) => state.triggerActiveTutorialStep);
  const triggerError = useAppStore((state) => state.learningCenterTriggerError);
  const leaveTutorial = useAppStore((state) => state.leaveActiveTutorial);
  const setStayOnFinish = useAppStore((state) => state.setLearningCenterStayOnFinish);
  const currentProject = useAppStore((state) => state.currentProject);
  const [triggerPending, setTriggerPending] = useState(false);

  const step = session?.step ?? null;
  const stepId = step?.id ?? null;
  const beats = step?.say ?? [];

  const [beat, setBeat] = useState(0);
  /*
   * Whether the step about to arrive should open at its last beat rather than
   * its first (#2138).
   *
   * Set by the back control on its way out of a step. A reader rewinding wants
   * the line immediately before the one they were on, which is the end of the
   * previous step, not its beginning — arriving at the top of it would make one
   * press back cost the whole step's reading again. The count is not known here
   * and does not need to be: `cursor` clamps, so "past the end" means "the end".
   */
  const [enterAtEnd, setEnterAtEnd] = useState(false);
  /*
   * A new step starts at its first beat.
   *
   * Keyed on the step's id rather than its index, because a tutorial the reader
   * re-enters lands on the same index with different text.
   */
  useEffect(() => {
    setBeat(enterAtEnd ? Number.MAX_SAFE_INTEGER : 0);
    setEnterAtEnd(false);
    // `enterAtEnd` is read, not depended on: it is a one-shot the arriving step
    // consumes, and listing it here would re-run this when it is cleared.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepId]);

  /*
   * A satisfied step points at nothing — unless the reader walked back to it.
   *
   * A highlight says "act on this"; once the condition holds, the reader has,
   * and a ring still around the New button reads as an instruction to press it
   * again — which is how a reader who had just made their plot came to make a
   * second one. What is left to do at that point is Continue.
   *
   * Behind the furthest step, that reasoning inverts (#2138). A revisited step
   * reports satisfied whatever its condition now says, so "satisfied" there
   * means "you did this once", not "you just did it" — and the ring is what the
   * step is *about*. Without this, walking back through a tutorial showed the
   * words with nothing pointed at.
   */
  const revisiting = session?.revisiting ?? false;
  /*
   * Where the reader is in the step's beats. Above the early returns because
   * the auto-advance effect below reads it, and a hook may not sit after a
   * conditional return.
   */
  const lastBeat = Math.max(0, beats.length - 1);
  const cursor = Math.min(beat, lastBeat);
  const onLastBeat = cursor >= lastBeat;
  const remaining = lastBeat - cursor;

  /*
   * FR-054c — a step that declared it moves on by itself.
   *
   * Here rather than on the backend for the same reason beat position is here:
   * the advance waits for the last beat, and which beat the reader is on is
   * frontend state (FR-011d). The backend cannot gate on something it is never
   * told, and telling it would put presentation state into the session.
   *
   * Never behind the reader: a revisited step reports satisfied whatever its
   * condition now says (#2138), so without that guard walking back into an
   * auto-advancing step would bounce straight forward again.
   *
   * `advanced` is keyed on the step's id, so this fires once per step however
   * many times the session re-reports the same satisfied step — otherwise a
   * step whose condition stays true posts a continue on every re-judgment.
   */
  const flow = { session, step, onLastBeat, revisiting };
  const [advanced, setAdvanced] = useState<string | null>(null);
  const autoAdvancing = advancesItself(flow);

  useEffect(() => {
    if (!autoAdvancing || stepId === null || advanced === stepId) return;
    setAdvanced(stepId);
    void continueStep();
  }, [autoAdvancing, stepId, advanced, continueStep]);

  const beatHighlight = step?.highlights?.[cursor] ?? null;
  /*
   * Where the target is, and separately whether it is ringed.
   *
   * The dialogue is *placed* against the target whatever the step's state, and
   * only the ring goes out when the step is satisfied. Tying the two together
   * meant that the moment a reader finished a step the rect became null, and
   * `placeCard`'s answer to "no target" is the bottom-right dock — so the chat
   * line jumped to the corner of the window for the frame or two before the
   * step advanced. It read as a flash in the corner, which is exactly what it
   * was.
   */
  const rect = useHighlightRect(beatHighlight);
  const ringed = step !== null && (!step.satisfied || revisiting) ? rect : null;
  /*
   * The canvas, followed the same way a highlight is: per frame, because React
   * Flow pans and zooms by transforming an ancestor and the bottom panel is
   * resizable by drag. Measuring once would leave the dialogue behind on both.
   */
  const canvas = useHighlightRect(STAGE_TARGET);
  const viewport = useViewport();

  if (!session) return null;
  /*
   * A finished tutorial has no dialogue. `useLearningCenter` opens the catalogue
   * on completion, which is where the reader goes next; a panel saying
   * "complete" beside it would be the same news twice, in the smaller of the
   * two places.
   */
  if (session.status === "complete") return null;
  /*
   * The Learning Center's own panel is the one surface this stays out of.
   *
   * The dialogue sits above the modal layer so a step stays readable while the
   * dialog it is talking about is open. The catalogue is the exception: it is
   * the tutorial's own full-screen surface, opened from this heading, and a
   * panel hovering over it points at nothing.
   */
  /*
   * A session that stopped says so wherever the reader is, and before anything
   * below can decide not to render.
   *
   * FR-044 keeps the record so the reader can be told. Every other surface here
   * is conditional — on the canvas being on screen, on the tutorial's project
   * being the open one — and an error is precisely the case where that project
   * may never have opened at all. A driver that failed on the first step then
   * left a reader pressing a tutorial that did nothing, with nothing on screen
   * to say why.
   */
  if (session.status === "error") {
    return (
      <TutorialProblemBanner
        message={session.error ?? "This tutorial stopped with an error."}
        onLeave={() => void leaveTutorial()}
        title={session.title}
      />
    );
  }
  if (learningCenterOpen) return null;
  /*
   * A tutorial bound to a project is dormant while that project is not open.
   *
   * The backend already draws this line — a session is only live in its own
   * project (FR-062), and `active_session` answers with nothing while some
   * other project is open, because judging a step against the user's own work
   * would complete tutorial steps in it. Closing the project from the menu is
   * the one path that does not reach the backend at all: it clears the
   * frontend's project and nothing else, so the session in the store is a
   * moment out of date and the character was still standing on the welcome
   * screen. Dormant, not over — reopening the project puts her back.
   *
   * A tutorial with no project of its own is never gated, for the reason
   * `_is_live` gives: it belongs to no project, so there is nothing for it to
   * disagree with.
   */
  const boundToProject = session.project_path !== null;
  const inItsOwnProject =
    currentProject !== null &&
    (session.project_id === null || currentProject.id === session.project_id);
  if (boundToProject && !inItsOwnProject) return null;

  const stage = stageBox(canvas, viewport);
  const placement = placeDialogue(rect, stage);
  /*
   * The compact form's own geometry: beside the lit target, in the window
   * rather than on the canvas. A step delivered as a chat line is pointing at
   * one small control, and it points by standing next to it — which only works
   * if it may leave the canvas, since half those controls are in the side and
   * bottom panels.
   */
  const card = placeCard(rect, viewport);

  // The questions the controls turn on, all in `stepFlow`.
  const mayContinue = canContinue(flow);
  const wantsAction = needsAction(flow);
  const atTheEnd = finishing(flow);

  /*
   * Finishing, recorded before it is posted.
   *
   * The session completes on the response, and the reaction to a completed
   * session is an effect in `useLearningCenter` that never sees this click —
   * so which button was pressed has to be in the store before the request
   * goes out, not after it comes back.
   */
  const finish = (stay: boolean) => {
    setStayOnFinish(stay);
    void continueStep();
  };

  /*
   * FR-011f — the expression this beat was written with.
   *
   * Read off the beat, not off the session. The face used to be derived from
   * the step's state, which meant it changed when the runtime changed its mind
   * rather than when the writing did; an author who wanted her surprised on the
   * second line of three had no way to say so.
   */
  const mood = moodAt(step?.say_moods, cursor);

  /*
   * One control for both kinds of going back (#2138).
   *
   * Within a step it is the previous beat, which is frontend state (FR-011d);
   * at the step's first beat it is the previous step, which is the backend's
   * trail. The reader is not making that distinction — they clicked past
   * something and want it back — so they are not asked to. It disappears only
   * where there is genuinely nothing behind: the first beat of the first step.
   */
  const goBack =
    cursor > 0
      ? () => setBeat(cursor - 1)
      : session.can_go_back
        ? () => {
            setEnterAtEnd(true);
            void backStep();
          }
        : null;

  const heading = (
    <StepHeading
      onBack={goBack}
      onLeave={() => void leaveTutorial()}
      onOpenCatalogue={openLearningCenter}
      progress={step ? { index: step.index, total: step.total } : null}
      title={step?.title ?? session.title}
    />
  );

  /*
   * The end of the tutorial asks; every other step tells.
   *
   * These two replace the step's controls rather than joining them, which
   * costs nothing: the last step is a reading step, so there is no trigger to
   * run and nothing for Check again to look at.
   */
  const controls = atTheEnd ? (
    <FinishChoice onOpenCatalogue={() => finish(false)} onStay={() => finish(true)} />
  ) : !wantsAction ? null : (
    <StepControls
      checkable={session.status === "active"}
      onCheckAgain={() => void evaluateStep()}
      onTrigger={() => {
        setTriggerPending(true);
        void triggerStep().finally(() => setTriggerPending(false));
      }}
      trigger={step?.trigger ?? null}
      triggerPending={triggerPending}
    />
  );

  return (
    <>
      <TargetHighlight rect={ringed} />
      <DialogueSurface
        controls={controls}
        heading={heading}
        line={beats[cursor] ?? ""}
        mood={mood}
        /*
         * One click carries the whole reading, and it is the only thing that
         * does: mid-step it is the next beat, and on the last beat of a step
         * the reader may leave it is the step itself. Not gated on whether the
         * step also shows controls — with Continue gone this is the only way
         * forward, and a step carrying a trigger would otherwise be a dead end.
         */
        onAdvance={
          remaining > 0
            ? () => setBeat(cursor + 1)
            : /*
               * Inert at the very end (#2135). The two buttons are the only way
               * out of the last step, because a stray click that closed the
               * reader's project would be the most expensive misfire here.
               */
              mayContinue && !atTheEnd
              ? () => void continueStep()
              : null
        }
        card={card}
        compact={step?.compacts?.[cursor] ?? false}
        placement={placement}
        stage={stage}
        problem={triggerError ?? null}
        remaining={remaining}
        speaker={MIO_NAME}
      />
    </>
  );
}
