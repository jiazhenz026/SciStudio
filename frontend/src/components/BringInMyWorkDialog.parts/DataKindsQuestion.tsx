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
import { DATA_KIND_GROUPS, Q1_LABEL, Q1_OTHER_LABEL, Q1_OTHER_PLACEHOLDER } from "./copy";

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
    /*
     * `tabIndex={-1}` makes the section itself a focus target. Paged, the
     * requirement "choose at least one kind of data, or write in your own" can
     * be satisfied by any of eight checkboxes or by the free-text field, so
     * when the user tries to move on without answering, the dialog puts them at
     * the top of the group rather than picking one of those and implying it is
     * the answer we wanted.
     */
    <section
      className="grid content-start gap-3 focus:outline-none"
      data-testid="work-import-q1"
      id="work-import-q1"
      tabIndex={-1}
    >
      <h3 className="font-display text-xl text-ink">{Q1_LABEL}</h3>

      {/*
       * FR-014 rests entirely on what is below this line now. A sentence used to
       * say "the two lists describe the same data in different ways, so picking
       * from both is normal"; it was cut as padding (owner, 2026-08-08), and
       * FR-014's own wording asks for the presets to be "visually grouped so it
       * is clear both may be selected, rather than presented as one flat list" —
       * a requirement about structure, which is what these two labelled,
       * bordered boxes with their own legends are. Flatten them, or drop the
       * legends, and the requirement is gone with no copy left to notice.
       */}
      <div className="grid gap-3 sm:grid-cols-2">
        {DATA_KIND_GROUPS.map((group) => (
          <fieldset
            key={group.id}
            className="grid gap-1 rounded-2xl border border-stone-300 px-3 py-2"
            data-testid={`work-import-data-kind-group-${group.id}`}
          >
            {/* The legend is load-bearing for FR-014, not a caption. */}
            <legend className="px-1 text-xs font-medium uppercase tracking-wide text-stone-600">
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

      <label className="mt-1 text-sm text-ink" htmlFor="work-import-data-kinds-other">
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
