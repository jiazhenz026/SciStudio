/**
 * ADR-053 Learning Center (#2057) — the active step surface (FR-089, FR-090).
 *
 * FR-089 requires the active step be shown without occluding the element it
 * refers to. This satisfies that by following: the card is placed beside the
 * step's target, on whichever side has room (`placeCard`), and the target is
 * ringed where it sits (`TargetHighlight`). A step pointing at nothing docks
 * the card in the corner and rings nothing.
 *
 * It replaced a strip in normal document flow, which satisfied the same
 * requirement by covering nothing anywhere. The strip's problem was not
 * occlusion but distance: it said "find the Load block in the palette" from the
 * top of the window, and finding it was left to the reader.
 *
 * It renders the step view the backend returned and nothing else. There is no
 * step content here and no judging: spec §4.1 puts both on the backend, and
 * FR-002 removed the five frontend predicates that used to do the judging by
 * reading the frontend's copy of the workflow.
 *
 * Steps do not advance on their own (FR-054a). The backend re-judges on the
 * engine events of FR-050 and reports whether the current step's condition
 * holds; Continue lights up, and the reader presses it when they are ready.
 * Automatic advance was the original design (User Story 1, acceptance 3) and
 * was reversed on 2026-08-10: a step that completes while its text is still
 * being read replaces that text with the next step's, and the reader has no way
 * to get it back.
 *
 * "Check again" is FR-053: it covers state no mapped event reaches, such as a
 * data file whose extension is outside the `file.changed` allowlist.
 */

import { GraduationCap, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useAppStore } from "../../store";

import { TargetHighlight } from "./TargetHighlight";
import { CARD_WIDTH, placeCard } from "./placeCard";
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
  const leaveTutorial = useAppStore((state) => state.leaveActiveTutorial);

  const step = session?.step ?? null;
  /*
   * A satisfied step points at nothing.
   *
   * A highlight says "act on this"; once the condition holds, the reader has,
   * and a ring still around the New button reads as an instruction to press it
   * again — which is how a reader who had just made their plot came to make a
   * second one. What is left to do at that point is Continue, and the card is
   * where that lives.
   */
  const rect = useHighlightRect(step && !step.satisfied ? step.highlight : null);
  const viewport = useViewport();

  if (!session) return null;
  /*
   * A finished tutorial has no card. `useLearningCenter` opens the catalogue on
   * completion, which is where the reader goes next; a card saying "complete"
   * beside it would be the same news twice, in the smaller of the two places.
   */
  if (session.status === "complete") return null;
  /*
   * The Learning Center's own panel is the one surface the card stays out of.
   *
   * The card sits above the modal layer so a step stays readable while the
   * dialog it is talking about is open. The catalogue is the exception: it is
   * the tutorial's own full-screen surface, opened from this card's title, and
   * a card hovering over it points at nothing.
   */
  if (learningCenterOpen) return null;

  const placement = placeCard(rect, viewport);
  const canContinue =
    session.status === "active" && step !== null && (step.satisfied || step.awaiting_continue);

  return (
    <>
      <TargetHighlight rect={rect} />

      {/*
       * A column with a height ceiling, so the buttons are always on screen.
       *
       * The step text is the one part whose length is unbounded — a scene-setting
       * step runs to five sentences — and a card that simply grew to fit pushed
       * its own Continue button past the bottom of the window, which made the
       * step impossible to finish rather than merely ugly. The prose scrolls
       * inside the middle row; the title and the buttons do not scroll, because
       * they are how the reader gets out.
       */}
      {/*
       * Above the product's modal layer (`z-50`), not level with it.
       *
       * A step whose instruction is "press New, choose New custom block" is at
       * its most useful while that dialog is open, and every dialog in this
       * product lays a dimming scrim over the whole window — level with it, the
       * card was greyed out and blurred at exactly the moment it was being
       * followed. It stays a small card in a corner or beside the target, so
       * being above the scrim costs the dialog nothing.
       */}
      <section
        aria-label="Tutorial step"
        className="fixed z-[60] flex flex-col rounded-xl border border-stone-200 bg-white p-4 shadow-xl"
        data-testid="tutorial-active-step"
        data-tutorial-card-side={placement.side ?? "docked"}
        style={{
          top: placement.top ?? undefined,
          bottom: placement.bottom ?? undefined,
          left: placement.left,
          width: CARD_WIDTH,
          maxHeight: placement.maxHeight,
        }}
      >
        <div className="flex min-h-0 flex-1 items-start gap-3 overflow-y-auto">
          <GraduationCap aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-ember" />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {/*
               * FR-011c — the step's own heading, falling back to the
               * tutorial's. Every step headed by the tutorial's name told the
               * reader the one thing they already knew and nothing about where
               * they were. Still the way back into the catalogue.
               */}
              <button
                className="truncate text-xs font-semibold text-ink underline-offset-2 hover:underline"
                onClick={openLearningCenter}
                type="button"
              >
                {step?.title ?? session.title}
              </button>
              {step ? (
                <span className="text-[0.7rem] text-stone-500">
                  Step {step.index + 1} of {step.total}
                </span>
              ) : null}
            </div>

            {session.status === "error" ? (
              <p className="mt-1 text-sm leading-6 text-red-700" data-testid="tutorial-step-error">
                {session.error ?? "This tutorial stopped with an error."}
              </p>
            ) : null}

            {step?.say ? <p className="mt-1 text-sm leading-6 text-stone-700">{step.say}</p> : null}

            {/*
             * `highlight` and `route_to` are not printed. They used to render as
             * "Look for: canvas" / "Go to: history", which named a thing instead
             * of showing it — and printed the raw target id at that. Both now
             * act: `App.tsx` opens the surface a step routes to, and
             * `TargetHighlight` rings what it highlights.
             */}
          </div>

          {/* FR-090 — leaving is possible at any step, and keeps the session. */}
          <button
            aria-label="Leave tutorial"
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink"
            onClick={() => void leaveTutorial()}
            title="Leave this tutorial — your place is kept"
            type="button"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>

        {/*
         * FR-054a — both buttons are always present, and Continue is the only
         * thing that moves the tutorial on.
         *
         * They do not appear and disappear with the step's state. A control
         * that is sometimes absent teaches the reader to hunt for it; one that
         * is always in the same corner, lit or grey, teaches them where the
         * tutorial's controls are and lets the lit/grey pair carry the one bit
         * of information that actually changes — whether this step is done.
         *
         * `disabled` follows the backend's `satisfied`, never a local
         * re-derivation of the condition (spec §4.1). A reading step is always
         * ready to continue, having no condition to meet (FR-012).
         */}
        <div className="mt-3 flex shrink-0 items-center justify-end gap-2">
          <button
            className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-stone-300 disabled:hover:text-stone-600"
            data-testid="tutorial-check-again"
            disabled={session.status !== "active"}
            onClick={() => void evaluateStep()}
            title="Re-check this step against the project"
            type="button"
          >
            <RefreshCw aria-hidden="true" className="size-3.5" />
            Check again
          </button>

          <button
            className="rounded-full bg-ink px-3 py-1 text-xs font-medium text-white transition hover:bg-pine disabled:cursor-not-allowed disabled:bg-stone-300 disabled:hover:bg-stone-300"
            data-testid="tutorial-continue"
            disabled={!canContinue}
            onClick={() => void continueStep()}
            title={
              canContinue
                ? "Go to the next step"
                : "This step is not done yet — finish it, or press Check again"
            }
            type="button"
          >
            Continue
          </button>
        </div>
      </section>
    </>
  );
}
