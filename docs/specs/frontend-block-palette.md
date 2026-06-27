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
  out:
    - Backend or schema changes (none — base_category, subcategory, ports, direction already exist on BlockSummary).
    - Per-block custom icons (still tracked as the categoryVisuals follow-up; palette keeps the category-icon fallback).
    - Plugin-shipped loader/saver blocks as distinct palette entries (consolidated into the unified core Load/Save).
    - Canvas BlockNode rendering (unchanged; this spec only consumes its categoryVisuals table).
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
  excludes:
    - frontend/src/components/nodes/BlockNode.parts/categoryVisuals.ts
tests:
  - frontend/src/components/BlockPalette.test.tsx
  - frontend/src/components/BlockPalette.parts/__tests__/paletteModel.test.ts
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
   as one flat grid with **no category sub-grouping**.
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

## 7. Out Of Scope

- No backend, schema, or `BlockSummary` contract change.
- No change to `categoryVisuals.ts` (consumed read-only) or to the canvas node.
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
