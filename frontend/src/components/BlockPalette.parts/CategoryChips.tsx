// Top-of-panel category filter chips — the shared `FilterChips` row supplied
// with the block base categories and the canvas per-category colour language.
//
// Specs: docs/specs/frontend-block-palette.md §5 Category Filter Chips.
//        docs/specs/adr-053-personal-tool-library.md §10.1 (shared chips),
//        §10.2 (`CATEGORY_KEYS` stays a block concept).

import { categoryVisuals } from "../nodes/BlockNode.parts/categoryVisuals";
import { FilterChips, type FilterChip } from "../palette/FilterChips";
import { CATEGORY_KEYS } from "./paletteModel";

const CATEGORY_CHIPS: readonly FilterChip[] = CATEGORY_KEYS.map((key) => {
  const visual = categoryVisuals[key];
  return {
    key,
    label: visual.label,
    background: visual.bg,
    border: visual.border,
    color: visual.fg,
  };
});

export interface CategoryChipsProps {
  active: readonly string[];
  onToggle: (key: string) => void;
}

export function CategoryChips({ active, onToggle }: CategoryChipsProps) {
  return (
    <FilterChips
      active={active}
      chips={CATEGORY_CHIPS}
      onToggle={onToggle}
      testId="palette-category-chips"
    />
  );
}
