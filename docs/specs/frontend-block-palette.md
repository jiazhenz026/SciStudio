---
spec_id: frontend-block-palette
title: "Block Palette — Category-Colored 2-Up Grid With Pinned Data I/O And Hover Detail"
status: Draft
feature_branch: feat/1797-palette-grid-redesign
created: 2026-06-27
input: "Issue #1797 — owner-directed redesign of the left BlockPalette (compact 2-up grid, reuse canvas category visuals, pinned Data I/O, type filter chips, hover detail popover)."
owners:
  - "@jiazhenz026"
related_adrs:
  - 50
related_specs: []
scope:
  in:
    - Left BlockPalette switches from tall full-width cards to a 2-column grid of compact mini-node tiles.
    - Each tile reuses the canvas per-category visual language (macaron swatch + lucide icon) via getCategoryVisual().
    - A pinned "Data I/O" section (core Load source + Save sink) renders at the top, never collapsed, lifted out of package grouping.
    - Top-of-panel category filter chips (io / process / code / app / ai / subworkflow) toggle a category filter.
    - Section ordering — Data I/O, then Built-in (core), then Custom, then plugin packages A→Z.
    - A hover detail popover anchored to the right of a tile showing icon, name, full description, and typed port signature.
    - The category sub-grouping layer, the always-on description line, and the "X in / Y out" text line are removed from the tile.
    - A one-shot opacity blink confirming a completed Reload, via a shared `useReloadFlash` hook also wired to the project tree Refresh.
  out:
    - Backend or schema changes (none — base_category, subcategory, ports, direction already exist on BlockSummary).
    - Per-block custom icons (still tracked as the categoryVisuals follow-up; palette keeps the category-icon fallback).
    - Plugin-shipped loader/saver blocks as distinct palette entries (consolidated into the unified core Load/Save).
    - Canvas BlockNode rendering (unchanged by #1797; §10 amendment (#1887) later reuses the shared hover-detail popover on canvas nodes).
    - Collapsed/rail palette mode redesign (the collapsed prop is preserved as-is, not re-themed).
governs:
  modules:
    - frontend/src/components/BlockPalette
  contracts: []
  entry_points: []
  files:
    - docs/specs/frontend-block-palette.md
    - frontend/src/components/BlockPalette.tsx
    - frontend/src/components/BlockPalette.parts
    - frontend/src/hooks/useReloadFlash.ts
    - frontend/src/components/ProjectTree.tsx
  excludes:
    - frontend/src/components/nodes/BlockNode.parts/categoryVisuals.ts
tests:
  - frontend/src/components/BlockPalette.test.tsx
  - frontend/src/components/BlockPalette.parts/__tests__/paletteModel.test.ts
  - frontend/src/hooks/__tests__/useReloadFlash.test.ts
acceptance_source: issue
language_source: en
---

# Block Palette — Category-Colored 2-Up Grid With Pinned Data I/O And Hover Detail

## 1. Change Summary

The left BlockPalette renders each block as a tall, full-width white card carrying
the block name, an always-on description, and a `X in / Y out` text line, grouped
three levels deep (package → category → block). The list grows very long, and the
block's category (io / process / code / app / ai / subworkflow) is not visible at a
glance — the category appears only as an uppercase text badge on a sub-group header.

Meanwhile the canvas node (ADR-050, `categoryVisuals.ts`) already encodes category
with a distinct macaron color + lucide icon per `base_category`. The palette does
not reuse it, so browsing and the canvas speak different visual languages.

This change rebuilds the palette to be compact and category-recognizable at a
glance by **reusing the canvas category visuals**: the palette becomes a 2-up grid
of mini-node tiles (the same swatch + icon you get on the canvas), with category
filter chips, a pinned Data I/O section, and a hover popover for detail. This is a
**frontend-only presentation change** — no schema, contract, or backend dependency.

## 2. Data Model — No Changes Needed

All inputs already exist on `BlockSummary` (`frontend/src/types/api.ts`):

| Need | Source field |
|---|---|
| Category color + icon | `base_category` via `getCategoryVisual()` |
| Package grouping | `package_name` / `type_name` prefix / `source` (existing `derivePackage`) |
| Load / Save detection | `base_category === "io"` and `input_ports.length === 0` (source) / `output_ports.length === 0` (sink) |
| Hover description | `description` |
| Hover port signature | `input_ports[] / output_ports[]` (`name`, `accepted_types[]`) |

The canvas visual table `categoryVisuals.ts` is consumed read-only via its existing
`getCategoryVisual(category)` export. No new schema field is introduced.

## 3. Tile (Grid Cell)

Each block renders as a compact mini-node tile, visually a shrunk canvas node:

- A square color **swatch** (~36px) using `visual.bg` / `visual.border`, containing
  the category **lucide icon** (~22px) in `visual.fg`. `visual` = `getCategoryVisual(block.base_category)`.
- The block **name** below the swatch, centered, `font-display`, 2-line clamp.
- The whole tile is `draggable` (unchanged drag payload contract) and a click adds
  the block (`onAddBlock`), preserving current behavior.
- Removed from the tile: the always-on `description` paragraph and the
  `X in / Y out` text line.

Tiles lay out in a 2-column grid (`grid-cols-2`) within each section. The existing
`collapsed` (rail) prop is preserved: when collapsed the panel keeps its current
minimal behavior and does not render the grid/chips/popover.

## 4. Sections And Ordering

The three-level package → category → block tree is replaced by a flat,
category-free ordering. Top to bottom:

1. **Data I/O** — pinned, never collapsed. Contains the core Load (io source,
   `input_ports.length === 0`) and Save (io sink, `output_ports.length === 0`)
   blocks, lifted out of their package group so they never appear twice.
2. **Built-in** — the remaining core blocks (`derivePackage` → "SciStudio Core"),
   as one flat grid with **no category sub-grouping**. Core blocks that use a
   dotted namespace but ship with core (the `ai.` namespace, e.g. `ai.agent`)
   resolve to Built-in rather than a standalone package.
3. **Custom** — user `source === "custom"` blocks.
4. **Plugin packages** — every other package, sorted **A→Z** by display name.

Built-in and plugin sections remain collapsible (existing package-collapse
behavior); Data I/O is always shown. Within every section, tiles sort
alphabetically by block name.

## 5. Category Filter Chips

A row of six chips (`io`, `process`, `code`, `app`, `ai`, `subworkflow`) renders
above the sections, each styled with that category's `bg`/`fg`/`border` from
`categoryVisuals`. Chips are a multi-select toggle:

- No chip active → show all categories (default).
- One or more active → show only blocks whose `base_category` is in the active set.
- The chip filter composes with the text search (AND): a block must satisfy both.
- The pinned Data I/O section follows the same filter (e.g. filtering to `process`
  hides Load/Save), but its **pinned position does not change**.

## 6. Hover Detail Popover

Hovering a tile opens a detail popover anchored to the **right** of the tile (the
palette is on the left edge, so the popover opens toward the canvas and does not
cover sibling tiles). It shows:

- The category swatch + icon and the block **name** (header).
- The full **description**.
- A **typed port signature**: one line per port as `name : Type`, where `Type` is
  the first entry of `accepted_types` (or `Any` when empty / the any-type marker),
  under `in` and `out` groupings.

The popover is hover-triggered with a short open delay (~150ms) and is
non-interactive (display only). It replaces the information previously shown
always-on (description) and adds the typed port contract, which the old text
`X in / Y out` line did not convey.

The popover is implemented as a standalone display-only component
(`components/BlockDetailPopover.tsx`, testid `block-detail-popover`) taking a
`BlockSummary` and a viewport-space `{ left, top }` anchor. It is shared with
the canvas, which reuses it for the on-node hover detail (§10, #1887).

## 7. Out Of Scope

- No backend, schema, or `BlockSummary` contract change.
- No change to `categoryVisuals.ts` (consumed read-only). The original #1797 work
  left the canvas node untouched; the §10 amendment (#1887) later reuses the
  shared popover on canvas nodes without otherwise changing node rendering.
- Per-block custom icons remain the separately tracked `categoryVisuals` follow-up.
- Collapsed/rail palette mode keeps its current minimal rendering; only the
  expanded palette is redesigned.

## 8. Test Plan

Pure ordering/detection/filter logic is extracted into a testable model module
(`BlockPalette.parts/paletteModel.ts`) and covered by
`BlockPalette.parts/__tests__/paletteModel.test.ts`:

- Load/Save detection by io + zero-port structural signal (not by name).
- Section ordering: Data I/O → Built-in → Custom → plugin packages A→Z.
- Data I/O lifted out of its package group (no duplicate rendering).
- Category-chip filter composes with text search (AND).

Component behavior is covered by the rewritten `BlockPalette.test.tsx`:

- Grid tiles render the category icon/swatch and the block name (no always-on
  description, no `in / out` text line).
- Data I/O section renders Load and Save pinned at the top.
- Activating a category chip filters the visible tiles.
- Hovering a tile reveals the detail popover with description and port signature.

Canvas hover-detail behavior (§10, #1887) is covered by
`nodes/BlockNode.parts/nodeDetailAnchor.test.ts` (right/left flip + top clamp of
the anchor) and `nodes/__tests__/BlockNode/hoverDetail.test.tsx` (dwell-delayed
open, description + typed ports, dismiss on leave, no-op without a summary).

## 9. Reload Flash

The palette Reload control gives an at-a-glance confirmation that the catalog
refreshed: a single fast opacity blink (1 → 0 → 1 over ~100ms, like a browser
refresh) across the whole palette body (search + chips + grid).

The blink is driven by a shared `useReloadFlash` hook. The hook arms on the
Reload click and fires only when the watched data (`blocks`) next changes — so
it confirms the refresh actually landed and does not fire on mount, on
background catalog syncs, or on a failed reload. It uses the Web Animations API
so the subtree is not remounted (section-collapse state is preserved), guarded
for environments without `Element.animate`.

The same hook is wired to the project tree Refresh control (watching the tree
nodes), so both side panels share one consistent reload feedback.

The hook is covered by `frontend/src/hooks/__tests__/useReloadFlash.test.ts`;
the palette wiring is covered by `BlockPalette.test.tsx`.

## 10. Canvas Node Hover Detail (#1887 Amendment)

Hovering a placed block node on the workflow canvas opens the same hover-detail
popover the palette uses, so a user can recall what a block does and its port
types without opening the BottomPanel Config tab. This amendment adds the canvas
trigger; it does not change the popover's content or the palette behavior above.

- **Reuse, not reimplementation.** The canvas renders the shared
  `BlockDetailPopover` (§6) with the node's existing `data.summary`
  (`BlockSummary`). No new fetch or backend change — the summary is already
  carried on the node.
- **Trigger and dwell.** The popover opens after a ~400ms hover dwell — longer
  than the palette's ~150ms so it does not flash while the user wires or drags
  nodes — and dismisses immediately when the cursor leaves the node. It is
  display-only and `pointer-events-none`.
- **Anchor (canvas-specific).** Unlike the palette (fixed left rail, always
  opens right), a canvas node can sit anywhere and the canvas pans/zooms, so the
  anchor is computed from the node's on-screen bounding rect by
  `computeNodeDetailAnchor` (`nodes/BlockNode.parts/nodeDetailAnchor.ts`):
  prefer the right side with an 8px gap, flip to the left when the 256px-wide
  card would overflow the right viewport edge (clamped off the left edge), and
  clamp the top into `[gap, viewportHeight − maxHeight]`. Reading the live
  on-screen rect keeps placement correct under any zoom/pan.
- **Coexistence.** The detail popover floats to the side of the 104×104 square;
  the existing `NodeActionToolbar` floats above it (ADR-050 §2.2). They do not
  overlap and both may be visible on hover.
- **Graceful no-op.** When `data.summary` is absent (e.g. an unresolved
  custom/plugin block), no popover opens.
