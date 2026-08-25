/**
 * ADR-053 Learning Center — the row above a step's line.
 *
 * Back, the step's name, how far in the reader is, and the way out. Split from
 * `ActiveStep` on the same seam `DialogueSurface` was: this decides nothing and
 * reads no store, so what is left in `ActiveStep` is the wiring and the rules.
 *
 * Every control here sits *inside* the dialogue panel, which is itself a click
 * target on beats that ask for nothing. `DialogueSurface` is what keeps a press
 * on one of them from also advancing the reading.
 */

import { ChevronLeft, X } from "lucide-react";

import { StepProgressRing } from "./StepProgressRing";

export interface StepHeadingProps {
  /**
   * Go back one line, or null when there is no line behind this one.
   *
   * Absent rather than inert at the very start of a tutorial: there is nothing
   * behind the first line of the first step, and a control offering to take the
   * reader there is offering nothing.
   */
  onBack: (() => void) | null;
  /** FR-011c — the step's own heading, already fallen back to the tutorial's. */
  title: string;
  /** The heading is also the way back into the catalogue. */
  onOpenCatalogue: () => void;
  /** Where the reader is, or null when the session is not on a step. */
  progress: { index: number; total: number } | null;
  /** FR-090 — leaving is possible at any step, and keeps the session. */
  onLeave: () => void;
}

const ICON_BUTTON =
  "inline-flex size-6 shrink-0 items-center justify-center rounded-full text-ink/40 transition hover:bg-ink/5 hover:text-ink";

export function StepHeading({
  onBack,
  title,
  onOpenCatalogue,
  progress,
  onLeave,
}: StepHeadingProps) {
  return (
    <div className="flex items-center gap-3">
      {onBack ? (
        <button
          aria-label="Go back"
          className={`-ml-1 ${ICON_BUTTON}`}
          data-testid="tutorial-back"
          onClick={onBack}
          title="Back to what she said before this"
          type="button"
        >
          <ChevronLeft aria-hidden="true" className="size-4" />
        </button>
      ) : null}

      {/*
       * FR-011c — the step's own heading rather than the tutorial's. Every step
       * headed by the tutorial's name told the reader the one thing they
       * already knew and nothing about where they were.
       */}
      <button
        className="truncate text-xs font-medium text-ink/55 underline-offset-2 hover:text-ink hover:underline"
        onClick={onOpenCatalogue}
        type="button"
      >
        {title}
      </button>

      {/*
       * Progress as a ring rather than a fraction (#2136).
       *
       * "1 / 16" is the first thing a reader sees, and what it tells them is
       * that there are fifteen more of these — the size of a commitment, at the
       * moment the tutorial is asking them to make one. The ring says the one
       * thing that helps, which is *some* of the way, and keeps the numbers for
       * its tooltip and its accessible name.
       */}
      {progress ? <StepProgressRing index={progress.index} total={progress.total} /> : null}

      <button
        aria-label="Leave tutorial"
        className={ICON_BUTTON}
        onClick={onLeave}
        title="Leave this tutorial — your place is kept"
        type="button"
      >
        <X aria-hidden="true" className="size-3.5" />
      </button>
    </div>
  );
}
