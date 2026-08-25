/**
 * ADR-053 Learning Center (#2135) — the last beat of the last step.
 *
 * Finishing a tutorial used to be one click with one outcome: the session
 * completed, the catalogue opened, and the project the reader had just spent
 * twenty minutes building closed behind it. That is the right ending for
 * somebody moving on to the next tutorial and the wrong one for somebody who
 * wants to keep poking at the workflow they made — and the last beat says both
 * are fine ("You can keep exploring in this project, or start your next one"),
 * so the ending should ask which.
 *
 * Buttons rather than the panel's own click, and the panel goes inert while
 * they are up: there is no default here worth guessing at, and a stray click
 * that closed the reader's project would be the most expensive misfire in the
 * tutorial.
 *
 * Presentational, like `StepControls` beside it: it decides nothing and reads
 * no store. Which of the two ran is `ActiveStep`'s to record before it posts
 * the continue.
 */

import { GraduationCap } from "lucide-react";

export interface FinishChoiceProps {
  /** Finish, and leave the reader in the project with everything they built. */
  onStay: () => void;
  /** Finish the way finishing has always worked: catalogue open, project closed. */
  onOpenCatalogue: () => void;
}

export function FinishChoice({ onStay, onOpenCatalogue }: FinishChoiceProps) {
  return (
    <>
      <button
        className="inline-flex items-center gap-1.5 rounded-full bg-pine px-3 py-1 text-xs font-medium text-white transition hover:bg-ink"
        data-testid="tutorial-finish-stay"
        onClick={onStay}
        title="Finish the tutorial and stay in this project"
        type="button"
      >
        Keep exploring
      </button>

      <button
        className="inline-flex items-center gap-1.5 rounded-full border border-ink/20 px-3 py-1 text-xs font-medium text-ink/70 transition hover:border-pine hover:text-pine"
        data-testid="tutorial-finish-catalogue"
        onClick={onOpenCatalogue}
        title="Finish the tutorial and go back to the Learning Center"
        type="button"
      >
        <GraduationCap aria-hidden="true" className="size-3.5" />
        Back to Learning Center
      </button>
    </>
  );
}
