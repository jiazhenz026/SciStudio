/**
 * ADR-053 spec 2 (#2001) — questions 2, 3 and 4 (FR-016 – FR-021).
 *
 * All three are free text about the user's own work. None asks which data types
 * the blocks should use, whether a step should be interactive, how ports are
 * shaped (FR-006), which environment the code runs in, how dependencies install,
 * or which interpreter is used (FR-007). The agent establishes all of that
 * itself; a first-day scientist can answer every field here.
 *
 * Each of these now has a page to itself, which changes two things and only two.
 *
 * The question is given room. One question per page means the page is mostly
 * empty, and that space goes to the question, its help line and its example
 * rather than to padding — the label is the size of a heading because on this
 * page it IS the heading, and the box is deep enough to invite more than a
 * clause. Nothing about the wording changes: these strings are reproduced to the
 * agent verbatim (spec §4.6), so what the user read and what the agent is told
 * they read stay the same.
 *
 * FR-020 — the skip control moved to the navigation row, beside Next, where it
 * reads as the second way to answer rather than as a box you tick when you give
 * up. What stays here is what a skip looks like when the user comes BACK to the
 * page: without `SKIPPED_NOTE` a returned-to skip is indistinguishable from a
 * blank they forgot, which is the exact reading FR-020 rules out. Typing takes
 * the skip back, so the note never becomes a trap.
 */
import { REQUIRED_MARKER, SKIPPED_NOTE } from "./copy";
import type { OptionalAnswer } from "./formState";

export interface FreeTextQuestionProps {
  id: string;
  label: string;
  help: string;
  placeholder: string;
  value: OptionalAnswer;
  /**
   * FR-016 / FR-017 — question 2 becomes required in no-codebase mode. A
   * required question offers no skip control at all, rather than a skip that
   * silently fails: the answer is the entire input to the session. The dialog
   * withholds the skip button from the navigation row for the same reason.
   */
  required?: boolean;
  onChange: (value: OptionalAnswer) => void;
}

export function FreeTextQuestion({
  id,
  label,
  help,
  placeholder,
  value,
  required = false,
  onChange,
}: FreeTextQuestionProps) {
  const skipped = !required && value.skipped;

  return (
    <section className="grid content-start gap-3" data-testid={`work-import-${id}`}>
      <label className="font-display text-xl text-ink" htmlFor={`work-import-${id}-input`}>
        {label}
        {required ? (
          <span
            className="ml-2 rounded-full bg-stone-200 px-2 py-0.5 align-middle text-xs font-normal text-stone-600"
            data-testid={`work-import-${id}-required`}
          >
            {REQUIRED_MARKER}
          </span>
        ) : null}
      </label>
      <p className="text-sm text-stone-600" data-testid={`work-import-${id}-help`}>
        {help}
      </p>
      {skipped ? (
        <p
          className="rounded-2xl bg-stone-100 px-3 py-2 text-xs text-stone-600"
          data-testid={`work-import-${id}-skipped`}
        >
          {SKIPPED_NOTE}
        </p>
      ) : null}
      <textarea
        id={`work-import-${id}-input`}
        className="min-h-[9rem] rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink"
        data-testid={`work-import-${id}-input`}
        placeholder={placeholder}
        value={value.text}
        required={required}
        /*
         * Typing un-skips. The box stays enabled while skipped so a user who
         * changes their mind on the way back does not have to find a control to
         * undo it first — and so nothing they wrote before skipping is lost.
         */
        onChange={(event) => onChange({ text: event.target.value, skipped: false })}
      />
    </section>
  );
}
