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
// `block-declared ?? category default ?? UNKNOWN`: a block that declares neither
// looks exactly as before. An unknown `ui_icon` name (not in the curated set
// below) silently falls back to the category icon — never an error, never a
// missing glyph. Custom SVG/asset glyphs are deferred (issue #1839 option b).
//
// #1988 (the grey puzzle did two jobs): everything that was not one of the six
// used to land on a single grey `Puzzle` body, which conflated two unrelated
// states. They are now separate visuals:
//
//   `unknown`    — a REGISTERED block whose class inherits `Block` directly, so
//                  the registry's `_infer_category` reports "unknown". It has
//                  ports, it runs, it is simply not one of the six. It gets a
//                  macaron of its own (periwinkle) and the `Blocks` glyph.
//   `unresolved` — a `block_type` that resolved to NOTHING here: package not
//                  installed, drop-in deleted, or an agent naming a block that
//                  does not exist. There is no class to ask, so there are no
//                  ports and no metadata. It is drawn as a DASHED hole in the
//                  canvas rather than a solid body, so it can never be mistaken
//                  for a block that works.
//
// `Puzzle` is retired from both: a puzzle piece reads as "missing", which is
// the wrong story for the first state and too mild for the second.

import { createElement, forwardRef, type ComponentProps, type CSSProperties } from "react";
// #1847: a block's `ui_icon` may now name ANY lucide glyph (PascalCase or
// kebab-case), not just a curated subset. For this desktop app the full
// namespace import is acceptable (offline bundle, no per-load download) and it
// sidesteps the vendored lucide build's empty `exports` map, which blocks the
// lazy `lucide-react/dynamic` subpath. Names resolve via `resolveIconByName`.
import * as LucideIcons from "lucide-react";
import {
  // Base-category default icons (the 6 core block kinds), resolved statically.
  AppWindow,
  Blocks,
  Code2,
  FileQuestionMark,
  FolderInput,
  FunctionSquare,
  Package,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface CategoryVisual {
  /** Icon rendered in the node body (a lucide glyph, optionally rotated). */
  Icon: LucideIcon;
  /** Soft macaron body background fill. */
  bg: string;
  /** Icon + accent colour (deeper shade of the same family). */
  fg: string;
  /** Resting body border colour (a touch deeper than `bg`). */
  border: string;
  /** Human label for the category (tooltip / a11y). */
  label: string;
  /**
   * #1988 — draw the body outline dashed instead of solid. Reserved for
   * `unresolved`: a dashed outline reads as "there is supposed to be a block
   * here", which a solid body never can.
   */
  dashed?: boolean;
}

// Saturated macaron fills — chosen to read clearly against the warm
// `canvas` (#f5f1e8) background while staying soft (not neon). Each base
// category gets a distinct hue; `fg` (icon/accent) is a deeper shade of the
// same family for AA contrast, `border` sits one step under the fill.

// #1988 — the seventh macaron. Periwinkle is the widest gap left in the wheel
// once io (sky), process (mint), code (violet), app (yellow), ai (coral) and
// subworkflow (pink) are placed, so a no-category block stays tellable apart
// from all six. Glyph/body contrast is 4.69, inside the 2.77–4.13 band the
// shipping six already occupy.
const UNKNOWN: CategoryVisual = {
  Icon: Blocks,
  bg: "#b5c4f2",
  fg: "#33499e",
  border: "#93a8e8",
  label: "Custom",
};

// #1988 — the unresolved state deliberately spends NO hue. Its body is a shade
// of the canvas itself under a dashed border, so it reads as an empty slot in
// the graph rather than as a seventh kind of block. Pairing it with the warning
// badge (see `flowNodeBuilder`) is what keeps the "this did not resolve" fact
// visible instead of hidden behind nicer styling.
const UNRESOLVED: CategoryVisual = {
  Icon: FileQuestionMark,
  bg: "#efeade",
  fg: "#8a8069",
  border: "#b8ae99",
  label: "Unresolved",
  dashed: true,
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
  // #1988 — a registered block that is none of the six (registry
  // `_infer_category` returns "unknown" for a direct `Block` subclass).
  unknown: UNKNOWN,
  // Retained alias: `custom` was the pre-#1988 sentinel for the same "no base
  // category" idea and is still what some persisted/older node data carries.
  custom: UNKNOWN,
  // #1988 — a `block_type` nothing in this environment could load.
  unresolved: UNRESOLVED,
};

/** PascalCase a kebab/snake/space name: "folder-down" -> "FolderDown". */
function toPascalCase(name: string): string {
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

/**
 * Resolve a Lucide icon NAME to a component from the FULL lucide set (#1847,
 * widening #1839's curated set). Accepts PascalCase ("FolderDown") or
 * kebab-case ("folder-down"), and tolerates a trailing ":<deg>" rotation suffix
 * (stripped here; applied by {@link getCategoryVisual}). Returns `undefined`
 * for an empty or unknown name so callers fall back to the category icon —
 * never an error, never a missing glyph.
 */
export function resolveIconByName(name: string | null | undefined): LucideIcon | undefined {
  if (!name) return undefined;
  const bare = name.split(":")[0]?.trim();
  if (!bare) return undefined;
  const pascal = /[-_\s]/.test(bare)
    ? toPascalCase(bare)
    : bare.charAt(0).toUpperCase() + bare.slice(1);
  const icon = (LucideIcons as Record<string, unknown>)[pascal];
  // Lucide icon exports are forwardRef objects; guard against non-icon exports
  // (e.g. `createLucideIcon`, `icons`) and unknown names.
  return typeof icon === "object" && icon !== null ? (icon as LucideIcon) : undefined;
}

/** Parse the optional ":<deg>" rotation suffix on a ui_icon spec (#1847). */
function parseIconRotation(spec: string | null | undefined): number {
  if (!spec) return 0;
  const parts = spec.split(":");
  if (parts.length < 2) return 0;
  const deg = Number.parseInt(parts[1], 10);
  return Number.isFinite(deg) ? ((deg % 360) + 360) % 360 : 0;
}

/** Wrap an icon so it renders with a baked-in CSS rotation transform (#1847). */
function withRotation(Base: LucideIcon, deg: number): LucideIcon {
  if (!deg) return Base;
  const Rotated = forwardRef<SVGSVGElement, Omit<ComponentProps<LucideIcon>, "ref">>(
    function RotatedIcon({ style, ...rest }, ref) {
      return createElement(Base, {
        ...rest,
        ref,
        style: { transform: `rotate(${deg}deg)`, ...(style as CSSProperties) },
      });
    },
  );
  return Rotated as LucideIcon;
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
 *   - `uiIcon` (any Lucide name, PascalCase or kebab-case, with an optional
 *     ":<deg>" rotation suffix — e.g. "folder-down" or "split:90") becomes the
 *     node icon; an unknown name keeps the category icon (#1847).
 * With neither override the category default is returned unchanged.
 */
export function getCategoryVisual(
  category: string | undefined,
  uiColor?: string | null,
  uiIcon?: string | null,
): CategoryVisual {
  const base = (category && categoryVisuals[category]) || UNKNOWN;
  if (!uiColor && !uiIcon) return base;

  const resolved = resolveIconByName(uiIcon);
  const overrideIcon = resolved ? withRotation(resolved, parseIconRotation(uiIcon)) : undefined;
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
