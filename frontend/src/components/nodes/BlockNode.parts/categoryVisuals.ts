// ADR-050 §2.1 (canvas polish, #1698) — per-base-category node visuals, with
// optional per-block overrides (#1839).
//
// The square canvas node shows the block's BASE category (io / process / code /
// app / ai / subworkflow) as:
//   - a single-colour lucide line icon (replaces the old emoji marks), and
//   - a soft "macaron" body background + matching border + icon colour.
//
// Colour is keyed off `base_category` so the six core block kinds are
// distinguishable at a glance; package blocks resolve to their owning base
// category.
//
// #1839 (per-block color + icon): a block may now declare its OWN node color
// (`ui_color`, a CSS hex) and/or icon (`ui_icon`, a Lucide icon NAME) on its
// backend `BlockSummary`. Resolution order is
// `block-declared ?? category default ?? CUSTOM`: a block that declares neither
// looks exactly as before. An unknown `ui_icon` name (not in the curated set
// below) silently falls back to the category icon — never an error, never a
// missing glyph. Custom SVG/asset glyphs are deferred (issue #1839 option b).

import {
  // Base-category icons.
  AppWindow,
  Code2,
  FolderInput,
  FunctionSquare,
  Package,
  Puzzle,
  Sparkles,
  // Curated extras a block author may name via `ui_icon` (#1839). Kept to a
  // bounded, already-bundled set rather than importing all of lucide-react.
  Activity,
  Atom,
  Binary,
  Box,
  Brain,
  Calculator,
  Cpu,
  Database,
  Dna,
  Filter,
  FlaskConical,
  Gauge,
  Image,
  LineChart,
  Microscope,
  ScatterChart,
  Sigma,
  Table,
  TestTube,
  Waves,
  Workflow,
  Zap,
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

// Curated, name-addressable Lucide set a block may select via `ui_icon` (#1839).
// Includes the base-category icons plus common science/data glyphs. Names are
// the PascalCase Lucide export names a block author writes (e.g. "Microscope").
const CURATED_ICONS: Record<string, LucideIcon> = {
  AppWindow,
  Code2,
  FolderInput,
  FunctionSquare,
  Package,
  Puzzle,
  Sparkles,
  Activity,
  Atom,
  Binary,
  Box,
  Brain,
  Calculator,
  Cpu,
  Database,
  Dna,
  Filter,
  FlaskConical,
  Gauge,
  Image,
  LineChart,
  Microscope,
  ScatterChart,
  Sigma,
  Table,
  TestTube,
  Waves,
  Workflow,
  Zap,
};

// Lowercased index for tolerant lookup (so "microscope" resolves "Microscope").
const CURATED_ICONS_LOWER: Record<string, LucideIcon> = Object.fromEntries(
  Object.entries(CURATED_ICONS).map(([name, Icon]) => [name.toLowerCase(), Icon]),
);

/**
 * Resolve a Lucide icon NAME (#1839) to a component from the curated set.
 * Returns `undefined` for an empty or unknown name so callers fall back to the
 * category icon (never an error, never a missing glyph).
 */
export function resolveIconByName(name: string | null | undefined): LucideIcon | undefined {
  if (!name) return undefined;
  return CURATED_ICONS[name] ?? CURATED_ICONS_LOWER[name.toLowerCase()];
}

const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Parse a #rgb / #rrggbb string to [r, g, b], or null if invalid. */
function parseHex(hex: string): [number, number, number] | null {
  if (!HEX_RE.test(hex)) return null;
  let h = hex.slice(1);
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const n = parseInt(h, 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

/** Multiply each channel toward black by `factor` (0..1) and return #rrggbb. */
function darken(rgb: [number, number, number], factor: number): string {
  const to2 = (v: number) =>
    Math.max(0, Math.min(255, Math.round(v * factor)))
      .toString(16)
      .padStart(2, "0");
  return `#${to2(rgb[0])}${to2(rgb[1])}${to2(rgb[2])}`;
}

/**
 * Resolve the visual for a base category (#1698), applying optional per-block
 * overrides (#1839):
 *   - `uiColor` (valid CSS hex) becomes the body fill, with `fg` (accent) and
 *     `border` derived as deeper shades — mirroring the category palette
 *     relationship. An invalid hex is ignored (category colors kept).
 *   - `uiIcon` (a curated Lucide name) becomes the node icon; an unknown name
 *     keeps the category icon.
 * With neither override the category default is returned unchanged.
 */
export function getCategoryVisual(
  category: string | undefined,
  uiColor?: string | null,
  uiIcon?: string | null,
): CategoryVisual {
  const base = (category && categoryVisuals[category]) || CUSTOM;
  if (!uiColor && !uiIcon) return base;

  const overrideIcon = resolveIconByName(uiIcon);
  const rgb = uiColor ? parseHex(uiColor) : null;

  return {
    ...base,
    Icon: overrideIcon ?? base.Icon,
    ...(rgb
      ? {
          bg: uiColor as string,
          fg: darken(rgb, 0.45),
          border: darken(rgb, 0.82),
        }
      : {}),
  };
}
