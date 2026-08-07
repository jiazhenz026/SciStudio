/**
 * ADR-053 spec 2 (#2001) — question 1 (FR-013 – FR-015).
 *
 * *What kind of data do you usually work with?* It is the context for every
 * other answer: the same work reads differently depending on whether its author
 * handles images or transcriptomics.
 *
 * FR-014 — the presets sit at two different levels of abstraction and are
 * therefore GROUPED. A scientist says "time series", not "Series". Presented as
 * one flat list the two readings of the same data compete, and a user who
 * should tick both ticks one. Two labelled groups plus the "pick from both is
 * normal" line make the double selection obviously allowed.
 *
 * FR-015 — nothing branches on these. They are context for the agent, never a
 * routing mechanism. There is deliberately no lookup from a preset to a type,
 * a package, or a code path anywhere below.
 */
import { DATA_KIND_GROUPS, Q1_HELP, Q1_LABEL, Q1_OTHER_LABEL, Q1_OTHER_PLACEHOLDER } from "./copy";

export interface DataKindsQuestionProps {
  selected: string[];
  other: string;
  onToggle: (option: string) => void;
  onOtherChange: (value: string) => void;
}

export function DataKindsQuestion({
  selected,
  other,
  onToggle,
  onOtherChange,
}: DataKindsQuestionProps) {
  return (
    <section className="grid gap-2" data-testid="work-import-q1">
      <h3 className="text-sm font-medium text-ink">{Q1_LABEL}</h3>
      <p className="text-xs text-stone-500">{Q1_HELP}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        {DATA_KIND_GROUPS.map((group) => (
          <fieldset
            key={group.id}
            className="grid gap-1 rounded-2xl border border-stone-300 px-3 py-2"
            data-testid={`work-import-data-kind-group-${group.id}`}
          >
            <legend className="px-1 text-xs uppercase tracking-wide text-stone-500">
              {group.legend}
            </legend>
            {group.options.map((option) => (
              <label key={option} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  data-testid={`work-import-data-kind-${option}`}
                  checked={selected.includes(option)}
                  onChange={() => onToggle(option)}
                />
                {option}
              </label>
            ))}
          </fieldset>
        ))}
      </div>

      <label className="text-sm text-ink" htmlFor="work-import-data-kinds-other">
        {Q1_OTHER_LABEL}
      </label>
      <input
        id="work-import-data-kinds-other"
        type="text"
        className="rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink"
        data-testid="work-import-data-kinds-other"
        placeholder={Q1_OTHER_PLACEHOLDER}
        value={other}
        onChange={(event) => onOtherChange(event.target.value)}
      />
    </section>
  );
}
