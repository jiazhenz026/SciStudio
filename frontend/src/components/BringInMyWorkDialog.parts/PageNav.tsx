/**
 * ADR-053 spec 2 (#2001) — the paged dialog's footer: where you are, and how
 * you move.
 *
 * The owner's complaint about the single scrolling page was that it is
 * unpleasant and users will not bother. Five pages of unknown length is its own
 * version of that, so the progress indicator is not decoration: it is the thing
 * that makes a paged form bearable. The user can see how many steps there are,
 * which one they are on, and — because completed steps are clickable — that
 * going back costs nothing.
 *
 * FR-020 — THE SKIP LIVES HERE, next to Next, and that placement is the whole
 * argument. On the scrolling page a skip was a checkbox under the box, and a
 * checkbox reads as a thing you tick when you have given up. As a peer of the
 * button that moves you on it reads as what FR-020 says it is: a second, equally
 * legitimate way to answer the question — the user telling the agent to work it
 * out. Its label and its consequence are the same words as before
 * (`SKIP_LABEL`, `SKIP_HELP`), because that copy is what makes the choice
 * legible and it is reproduced to the agent.
 */
import { BACK_LABEL, PROGRESS_LABEL, SKIP_HELP, SKIP_LABEL, stepStatus } from "./copy";

export interface PageNavAction {
  label: string;
  testId: string;
  disabled: boolean;
  onClick: () => void;
}

export interface PageNavProps {
  /** 0-based index of the page on screen. */
  stepIndex: number;
  /** One title per page, in order. */
  titles: readonly string[];
  /**
   * Jump to a step. The dialog clamps the target, so this may land the user on
   * an earlier page than the one they clicked (see `furthestReachablePage`).
   */
  onGoTo: (index: number) => void;
  /** Null on the first page, where there is nothing behind. */
  onBack: (() => void) | null;
  /** Present only on a page whose question may be skipped (FR-020). */
  skip: { testId: string; onSkip: () => void } | null;
  /**
   * `Next`, or `Start session` on the last page. Null when there is no forward
   * move at all — the last page with no usable agent, where FR-005 puts the
   * availability guidance in place of a start action.
   */
  action: PageNavAction | null;
}

export function PageNav({ stepIndex, titles, onGoTo, onBack, skip, action }: PageNavProps) {
  const total = titles.length;

  return (
    <div className="grid gap-3" data-testid="work-import-nav">
      <nav aria-label={PROGRESS_LABEL} data-testid="work-import-progress">
        <ol className="flex items-center gap-1.5">
          {titles.map((title, index) => {
            const done = index < stepIndex;
            const current = index === stepIndex;
            return (
              <li key={title} className="flex-1">
                <button
                  type="button"
                  data-testid={`work-import-step-${index + 1}`}
                  aria-current={current ? "step" : undefined}
                  onClick={() => onGoTo(index)}
                  className={`h-1.5 w-full rounded-full transition-colors ${
                    current ? "bg-ink" : done ? "bg-stone-400" : "bg-stone-200"
                  }`}
                >
                  {/*
                   * The bar is the whole control, so the accessible name has to
                   * carry what the colour says. Sighted users get the same two
                   * facts from the status line below it.
                   */}
                  <span className="sr-only">{`${stepStatus(index + 1, total)} — ${title}`}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="mt-2 text-xs text-stone-500" data-testid="work-import-step-status">
          {`${stepStatus(stepIndex + 1, total)} · ${titles[stepIndex]}`}
        </p>
      </nav>

      <div className="flex items-center justify-between gap-3">
        {/*
         * Back is rendered on every page and only disabled on the first, rather
         * than appearing and disappearing: a control that moves as you page is
         * a control you have to find again each time.
         */}
        <button
          type="button"
          className="rounded-full border border-stone-300 px-4 py-2 text-sm text-ink hover:bg-stone-100 disabled:opacity-40"
          data-testid="work-import-back"
          disabled={onBack === null}
          onClick={() => onBack?.()}
        >
          {BACK_LABEL}
        </button>

        <div className="flex items-center gap-2">
          {skip ? (
            <button
              type="button"
              className="rounded-full border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-100"
              data-testid={skip.testId}
              onClick={skip.onSkip}
            >
              {SKIP_LABEL}
            </button>
          ) : null}
          {action ? (
            <button
              type="button"
              className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 hover:bg-pine disabled:opacity-50"
              data-testid={action.testId}
              disabled={action.disabled}
              onClick={action.onClick}
            >
              {action.label}
            </button>
          ) : null}
        </div>
      </div>

      {/*
       * What skipping does, said where the skip is. FR-020's "legitimate choice"
       * half is carried by this sentence: the agent is told, so the user is
       * handing it a decision rather than leaving a hole.
       */}
      {skip ? (
        <p className="text-right text-xs text-stone-500" data-testid="work-import-skip-help">
          {SKIP_HELP}
        </p>
      ) : null}
    </div>
  );
}
