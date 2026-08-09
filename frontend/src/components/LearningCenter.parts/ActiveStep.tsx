/**
 * ADR-053 Learning Center (#2057) — the active step surface (FR-089, FR-090).
 *
 * FR-089 requires the active step be shown somewhere that does not occlude the
 * canvas element it refers to, because most steps ask the user to act on the
 * canvas or the palette — a floating card sitting over the thing a step says to
 * drag a block onto is the one placement the requirement rules out. So this
 * renders as a strip in normal document flow: `App.tsx` mounts it between the
 * toolbar and the workspace, where it takes its own height and covers nothing.
 *
 * It renders the step view the backend returned and nothing else. There is no
 * step content here and no judging: spec §4.1 puts both on the backend, and
 * FR-002 removed the five frontend predicates that used to do the judging by
 * reading the frontend's copy of the workflow.
 *
 * Steps advance on their own. A condition that holds satisfies its step with no
 * click to confirm (User Story 1, acceptance 3) — the backend re-evaluates on
 * the engine events of FR-050 and pushes the next step. The only step carrying
 * a continue button is the reading case, `awaiting_continue` (FR-012). The
 * "Check again" button is FR-053, not a confirmation: it covers state no mapped
 * event reaches, such as a data file whose extension is outside the
 * `file.changed` allowlist.
 */

import { CheckCircle2, GraduationCap, RefreshCw, X } from "lucide-react";

import { useAppStore } from "../../store";

export function ActiveStep() {
  const session = useAppStore((state) => state.learningCenterSession);
  const openLearningCenter = useAppStore((state) => state.openLearningCenter);
  const evaluateStep = useAppStore((state) => state.evaluateActiveTutorialStep);
  const continueStep = useAppStore((state) => state.continueActiveTutorialStep);
  const leaveTutorial = useAppStore((state) => state.leaveActiveTutorial);

  if (!session) return null;

  const { step } = session;

  return (
    <section
      aria-label="Tutorial step"
      className="flex shrink-0 items-start gap-3 border-b border-stone-200 bg-[linear-gradient(90deg,_rgba(240,106,68,0.06),_transparent_60%)] px-4 py-2.5"
      data-testid="tutorial-active-step"
    >
      <GraduationCap aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-ember" />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <button
            className="truncate text-xs font-semibold text-ink underline-offset-2 hover:underline"
            onClick={openLearningCenter}
            type="button"
          >
            {session.title}
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

        {session.status === "complete" ? (
          <p className="mt-1 inline-flex items-center gap-1.5 text-sm leading-6 text-pine">
            <CheckCircle2 aria-hidden="true" className="size-4" />
            Tutorial complete.
          </p>
        ) : null}

        {step?.say ? <p className="mt-1 text-sm leading-6 text-stone-700">{step.say}</p> : null}

        {/*
         * `highlight` and `route_to` are the backend's pointers at where the
         * user should be looking. They are shown as words rather than acted on:
         * turning them into a highlight ring or a panel switch needs an agreed
         * vocabulary of element and surface ids, which the HTTP contract does
         * not carry. Showing them keeps the guidance the backend sent instead
         * of dropping it on the floor.
         */}
        {step?.route_to ? (
          <p className="mt-1 text-xs text-stone-500">Go to: {step.route_to}</p>
        ) : null}
        {step?.highlight ? (
          <p className="mt-1 text-xs text-stone-500">Look for: {step.highlight}</p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {step?.awaiting_continue ? (
          <button
            className="rounded-full bg-ink px-3 py-1 text-xs font-medium text-white transition hover:bg-pine"
            onClick={() => void continueStep()}
            type="button"
          >
            Continue
          </button>
        ) : null}

        {session.status === "active" && !step?.awaiting_continue ? (
          <button
            className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
            onClick={() => void evaluateStep()}
            title="Re-check this step against the project"
            type="button"
          >
            <RefreshCw aria-hidden="true" className="size-3.5" />
            Check again
          </button>
        ) : null}

        {/* FR-090 — leaving is possible at any step, and keeps the session. */}
        <button
          aria-label="Leave tutorial"
          className="inline-flex size-7 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink"
          onClick={() => void leaveTutorial()}
          title="Leave this tutorial — your place is kept"
          type="button"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>
    </section>
  );
}
