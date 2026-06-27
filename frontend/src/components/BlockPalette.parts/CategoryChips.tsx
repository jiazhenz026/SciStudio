// Top-of-panel category filter chips, styled with the canvas per-category
// color language. Multi-select toggle; an empty active set means "all".
//
// Spec: docs/specs/frontend-block-palette.md §5 Category Filter Chips.

import { categoryVisuals } from "../nodes/BlockNode.parts/categoryVisuals";
import { CATEGORY_KEYS } from "./paletteModel";

export interface CategoryChipsProps {
  active: readonly string[];
  onToggle: (key: string) => void;
}

export function CategoryChips({ active, onToggle }: CategoryChipsProps) {
  const activeSet = new Set(active);

  return (
    <div className="mt-3 flex flex-wrap gap-1" data-testid="palette-category-chips">
      {CATEGORY_KEYS.map((key) => {
        const visual = categoryVisuals[key];
        const on = activeSet.has(key);
        return (
          <button
            aria-pressed={on}
            className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide transition"
            key={key}
            onClick={() => onToggle(key)}
            style={
              on
                ? { backgroundColor: visual.bg, borderColor: visual.border, color: visual.fg }
                : { backgroundColor: "transparent", borderColor: "#e7e5e4", color: "#78716c" }
            }
            type="button"
          >
            {visual.label}
          </button>
        );
      })}
    </div>
  );
}
