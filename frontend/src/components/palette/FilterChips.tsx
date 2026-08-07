// The one palette filter-chip row — a multi-select toggle where an empty
// active set means "all".
//
// Spec: docs/specs/adr-053-personal-tool-library.md §10.1 (filter chips,
// generalised from `CategoryChips`). The chip vocabulary stays surface-owned:
// the Blocks tab supplies its base categories (§10.2 keeps `CATEGORY_KEYS` a
// block concept), the Data types tab supplies its own facets.

export interface FilterChip {
  /** Value toggled in the active set. */
  key: string;
  /** Chip caption. */
  label: string;
  /** Fill applied while the chip is active. */
  background: string;
  /** Border applied while the chip is active. */
  border: string;
  /** Text colour applied while the chip is active. */
  color: string;
}

export interface FilterChipsProps {
  chips: readonly FilterChip[];
  active: readonly string[];
  onToggle: (key: string) => void;
  testId?: string;
}

export function FilterChips({ chips, active, onToggle, testId }: FilterChipsProps) {
  const activeSet = new Set(active);

  return (
    <div className="mt-3 flex flex-wrap gap-1" data-testid={testId}>
      {chips.map((chip) => {
        const on = activeSet.has(chip.key);
        return (
          <button
            aria-pressed={on}
            className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide transition"
            key={chip.key}
            onClick={() => onToggle(chip.key)}
            style={
              on
                ? { backgroundColor: chip.background, borderColor: chip.border, color: chip.color }
                : { backgroundColor: "transparent", borderColor: "#e7e5e4", color: "#78716c" }
            }
            type="button"
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
