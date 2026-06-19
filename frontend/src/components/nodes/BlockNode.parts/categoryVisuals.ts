// ADR-050 §2.1 (canvas polish, #1698) — per-base-category node visuals.
//
// The square canvas node shows the block's BASE category (io / process / code /
// app / ai / subworkflow) as:
//   - a single-colour lucide line icon (replaces the old emoji marks), and
//   - a soft "macaron" body background + matching border + icon colour.
//
// Colour is keyed off `base_category` so the six core block kinds are
// distinguishable at a glance; package blocks resolve to their owning base
// category. This is a FRONTEND presentation table only — it adds no schema
// field and no backend dependency.
//
// FOLLOW-UP (per-block custom icons): a block declaring its OWN icon needs a
// backend `icon` field on the block schema (BlockSummary/BlockSchemaResponse)
// so packages can ship their own glyphs; that is tracked separately and out of
// scope for this frontend-only PR. Until then the frontend falls back to these
// category icons.

import {
  AppWindow,
  Code2,
  FolderInput,
  FunctionSquare,
  Package,
  Puzzle,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface CategoryVisual {
  /** lucide line icon rendered in the node body. */
  Icon: LucideIcon;
  /** Soft macaron body background fill. */
  bg: string;
  /** Icon + accent colour (deeper shade of the same family). */
  fg: string;
  /** Resting body border colour (a touch deeper than `bg`). */
  border: string;
  /** Human label for the category (tooltip / a11y). */
  label: string;
}

// Saturated macaron fills — chosen to read clearly against the warm
// `canvas` (#f5f1e8) background while staying soft (not neon). Each base
// category gets a distinct hue; `fg` (icon/accent) is a deeper shade of the
// same family for AA contrast, `border` sits one step under the fill.
const CUSTOM: CategoryVisual = {
  Icon: Puzzle,
  bg: "#c9d1d9",
  fg: "#4f5b66",
  border: "#aeb9c4",
  label: "Custom",
};

export const categoryVisuals: Record<string, CategoryVisual> = {
  io: { Icon: FolderInput, bg: "#9fd4ee", fg: "#176684", border: "#74c1e3", label: "IO" },
  process: {
    Icon: FunctionSquare,
    bg: "#9fdcbb",
    fg: "#1f6e54",
    border: "#73cda0",
    label: "Process",
  },
  code: { Icon: Code2, bg: "#c6b8f0", fg: "#5a44a8", border: "#a892e8", label: "Code" },
  app: { Icon: AppWindow, bg: "#fae28e", fg: "#8a6516", border: "#f1d062", label: "App" },
  ai: { Icon: Sparkles, bg: "#f9b8a0", fg: "#c2502c", border: "#f29c7e", label: "AI" },
  subworkflow: {
    Icon: Package,
    bg: "#eebcd0",
    fg: "#b04a78",
    border: "#e49dbe",
    label: "Subworkflow",
  },
  custom: CUSTOM,
};

/** Resolve the visual for a base category, falling back to the custom glyph. */
export function getCategoryVisual(category: string | undefined): CategoryVisual {
  return (category && categoryVisuals[category]) || CUSTOM;
}
