/**
 * ADR-053 spec 2 (#2001) — questions 2, 3 and 4 (FR-016 – FR-021).
 *
 * All three are free text about the user's own work. None asks which data types
 * the blocks should use, whether a step should be interactive, how ports are
 * shaped (FR-006), which environment the code runs in, how dependencies install,
 * or which interpreter is used (FR-007). The agent establishes all of that
 * itself; a first-day scientist can answer every field here.
 *
 * FR-020 — the skip is a CHOICE, not an abandoned field. It has its own control,
 * its own label ("let the agent work this out"), and a sentence saying what
 * happens as a result. A user who skips is telling the agent something; the copy
 * has to read that way or the skip becomes a thing you feel bad about.
 */
import { REQUIRED_MARKER, SKIP_HELP, SKIP_LABEL } from "./copy";
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
   * silently fails: the answer is the entire input to the session.
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
    <section className="grid gap-2" data-testid={`work-import-${id}`}>
      <label className="text-sm font-medium text-ink" htmlFor={`work-import-${id}-input`}>
        {label}
        {required ? (
          <span
            className="ml-2 rounded-full bg-stone-200 px-2 py-0.5 text-xs font-normal text-stone-600"
            data-testid={`work-import-${id}-required`}
          >
            {REQUIRED_MARKER}
          </span>
        ) : null}
      </label>
      <p className="text-xs text-stone-500" data-testid={`work-import-${id}-help`}>
        {help}
      </p>
      <textarea
        id={`work-import-${id}-input`}
        className="min-h-[5rem] rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink disabled:bg-stone-100 disabled:text-stone-400"
        data-testid={`work-import-${id}-input`}
        placeholder={placeholder}
        value={value.text}
        disabled={skipped}
        required={required}
        onChange={(event) => onChange({ ...value, text: event.target.value })}
      />
      {required ? null : (
        <label className="flex items-start gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="mt-1"
            data-testid={`work-import-${id}-skip`}
            checked={value.skipped}
            onChange={(event) => onChange({ ...value, skipped: event.target.checked })}
          />
          <span>
            {SKIP_LABEL}
            <span className="block text-xs text-stone-500">{SKIP_HELP}</span>
          </span>
        </label>
      )}
    </section>
  );
}
