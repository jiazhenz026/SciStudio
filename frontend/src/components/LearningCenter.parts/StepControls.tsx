/**
 * ADR-053 Learning Center — the buttons a step shows when it wants something.
 *
 * Rendered only on a beat that asks the reader to act: a trigger to run, or a
 * condition they have to go and satisfy. Every other beat gets the panel's own
 * "Click to continue…" instead, and `ActiveStep` decides which by passing these
 * or not.
 *
 * **There is no Continue button here, and that is the point.** Moving on is
 * always the panel's own click (FR-054b) — a button that appeared only once the
 * step was finished, beside a prompt that says the same thing, was two ways to
 * do one thing and the reader had to work out which. What is left are the two
 * controls that do something the panel cannot: run this step's action, and ask
 * the backend to look again.
 *
 * Presentational, like `StepHeading` and `DialogueSurface`: it reads no store
 * and judges nothing. `satisfied` in particular is never re-derived here —
 * spec §4.1 puts that on the backend, and FR-002 removed the frontend
 * predicates that used to duplicate it.
 */

import { RefreshCw } from "lucide-react";

export interface StepControlsProps {
  /** #2061 — the step's own button, labeled by the manifest, or null. */
  trigger: { label: string } | null;
  /** True while the trigger's actions are in flight on the backend. */
  triggerPending: boolean;
  onTrigger: () => void;
  /** FR-053 — the explicit re-check, for state no mapped event reaches. */
  onCheckAgain: () => void;
  /** False once the session has stopped; the re-check has nothing to ask. */
  checkable: boolean;
}

export function StepControls({
  trigger,
  triggerPending,
  onTrigger,
  onCheckAgain,
  checkable,
}: StepControlsProps) {
  return (
    <>
      {/*
       * #2061 — it runs the trigger's actions on the backend and re-renders the
       * re-judged session; a failure is shown in the panel, and pressing again
       * retries (FR-060's trigger revision — the session is never ended by it).
       */}
      {trigger ? (
        <button
          className="inline-flex items-center gap-1.5 rounded-full bg-pine px-3 py-1 text-xs font-medium text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-40"
          data-testid="tutorial-trigger"
          disabled={triggerPending}
          onClick={onTrigger}
          type="button"
        >
          {trigger.label}
        </button>
      ) : null}

      <button
        className="inline-flex items-center gap-1.5 rounded-full border border-ink/20 px-3 py-1 text-xs font-medium text-ink/70 transition hover:border-pine hover:text-pine disabled:cursor-not-allowed disabled:opacity-40"
        data-testid="tutorial-check-again"
        disabled={!checkable}
        onClick={onCheckAgain}
        title="Re-check this step against the project"
        type="button"
      >
        <RefreshCw aria-hidden="true" className="size-3.5" />
        Check again
      </button>
    </>
  );
}
