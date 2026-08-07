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
  - 53
related_specs:
  - adr-053-personal-tool-library
scope:
  in:
    - Left BlockPalette switches from tall full-width cards to a 2-column grid of compact mini-node tiles.
    - Each tile reuses the canvas per-category visual language (macaron swatch + lucide icon) via getCategoryVisual().
    - A pinned "Data I/O" section (core Load source + Save sink) renders at the top, never collapsed, lifted out of package grouping.
    - Top-of-panel category filter chips (io / process / code / app / ai / subworkflow) toggle a category filter.
    - Section ordering — Data I/O, then Built-in (core), then My Library (user tier), then This Project (project tier), then plugin packages A→Z, grouped by origin tier first and package second (ADR-053 §9.1).
    - My Library and This Project render even when empty, each with one line stating what the section is for (ADR-053 FR-037).
    - A hover detail popover anchored to the right of a tile showing icon, name, full description, and typed port signature; interactive in the palette so it can hold an action row (ADR-053 §9.3).
    - A shared section/filter/tile/chip/popover helper set the Data types tab reuses (ADR-053 §10.1).
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
    - frontend/src/components/BlockDetailPopover.tsx
    - frontend/src/components/palette
    - frontend/src/hooks/useReloadFlash.ts
    - frontend/src/components/ProjectTree.tsx
  excludes:
    - frontend/src/components/nodes/BlockNode.parts/categoryVisuals.ts
tests:
  - frontend/src/components/BlockPalette.test.tsx
  - frontend/src/components/BlockPalette.parts/__tests__/paletteModel.test.ts
  - frontend/src/components/palette/__tests__/sections.test.ts
  - frontend/src/components/palette/__tests__/useHoverPopover.test.tsx
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
category-free ordering. The panel is titled **Blocks**, matching its left-panel
tab (ADR-053 FR-034), and its sections run top to bottom:

1. **Data I/O** — pinned, never collapsed. Contains the core Load (io source,
   `input_ports.length === 0`) and Save (io sink, `output_ports.length === 0`)
   blocks, lifted out of their group so they never appear twice. The lift wins
   over the tier split below: a Load/Save block is pinned here whatever origin
   it resolves to.
2. **Built-in** — the remaining core blocks (`derivePackage` → "SciStudio Core"),
   as one flat grid with **no category sub-grouping**. Core blocks that use a
   dotted namespace but ship with core (the `ai.` namespace, e.g. `ai.agent`)
   resolve to Built-in rather than a standalone package.
3. **My Library** — blocks resolved to the user-wide tier
   (`~/.scistudio/blocks/`, `origin === "user"`).
4. **This Project** — blocks resolved to the project-local tier
   (`{project}/blocks/`, `origin === "project"`).
5. **Plugin packages** — every other package, sorted **A→Z** by display name.

Built-in and plugin sections remain collapsible (existing package-collapse
behavior); Data I/O is always shown. Within every section, tiles sort
alphabetically by block name.

### 4.1 Grouping Is By Origin Tier First, Package Second (ADR-053 FR-038)

`buildPaletteSections` used to group solely by `derivePackage`, which put every
tier-1 drop-in into one `Custom` section. It now groups by **origin tier
first** and by package only inside the package family:

| Resolved `origin` | Section |
|---|---|
| `user` | My Library |
| `project` | This Project |
| `custom` | This Project (see below) |
| `builtin` / `package` | `derivePackage(block)` — Built-in or the plugin package |

`origin` arrives on the block list response (ADR-053 FR-004). `custom` is the
FR-002 fallback for a tier-1 block whose `file_path` resolves to neither root
(absent path, a symlink escaping both, a differing Windows drive); it renders
under **This Project** because an unresolvable drop-in is not known to be
reusable across projects, and filing it under a section that promises
cross-project reuse would be a claim the backend did not make. A payload
carrying no recognised `origin` at all — a backend that predates the tier split
— falls back to the legacy `source` label and lands in the same place, so the
palette degrades rather than breaking.

`derivePackage` no longer has a `Custom` branch: tier-1 blocks are routed by
origin before package resolution runs.

### 4.2 Tier Empty States (ADR-053 FR-037)

**My Library** and **This Project** render even when they contain no blocks,
each carrying one line stating what the section is for:

> **My Library** — No blocks of your own yet. Save a block here and every
> project can use it.
>
> **This Project** — No blocks in this project yet. Blocks you add here stay
> with this project.

This is load-bearing rather than polish. For a user who has never heard of a
personal library, the empty section is the only moment they are guaranteed to
be looking at the place it would live. Every other section — Data I/O,
Built-in, and the plugin packages — keeps the ordinary omit-when-empty
behaviour.

The two empty states are suppressed while a search term or a category chip is
narrowing the grid. Under an active filter an empty section says nothing about
the library and everything about the query, and "No blocks of your own yet"
would assert something false about a section whose contents were merely
filtered away. Filtering otherwise treats the tier sections exactly like the
package sections.

### 4.3 Shared Section Model

The grouping skeleton is generic and shared with the Data types tab
(ADR-053 §10.1, FR-047): `buildSections<T>(items, groupOf, pinnedOrder,
compare)` and `filterItems<T>(items, search, toHaystack)` live in
`components/palette/sections.ts` and know nothing about blocks. Both surfaces
group primarily by origin tier, so one skeleton fits both with no per-surface
special-casing. `derivePackage`, `isIoSource` / `isIoSink` / `isDataIoBlock`,
`CATEGORY_KEYS`, and `portSignature` stay block-side per ADR-053 §10.2.

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

The popover is hover-triggered with a short open delay (~150ms). It replaces
the information previously shown always-on (description) and adds the typed
port contract, which the old text `X in / Y out` line did not convey.

The popover is implemented as a shared card shell
(`components/palette/DetailPopover.tsx`) composed by
`components/BlockDetailPopover.tsx` (testid `block-detail-popover`) with a
`BlockSummary` and a viewport-space `{ left, top }` anchor. One implementation
serves both palette surfaces (ADR-053 FR-046) and the canvas, which reuses it
for the on-node hover detail (§10, #1887).

### 6.1 The Popover Is Interactive (ADR-053 FR-044 – FR-046)

The palette popover was originally display-only, rendered with
`pointer-events-none`, and its visibility was driven entirely by the tile.
Nothing inside it could be clicked, which blocked the promotion action ADR-053
§6.2 places there (entry point E5).

- The palette card accepts pointer events and **maintains its own hover
  state**: it cancels the pending close when the pointer enters it.
- The `POPOVER_GAP` between tile and card is dead space with no element under
  the cursor, so leaving the tile schedules the close after a short grace
  period (`POPOVER_CLOSE_DELAY_MS`) rather than closing at once. Without the
  grace period the card would be unreachable and interactivity would be
  theoretical.
- The open delay, close grace, gap, and max height live in
  `components/palette/hoverPopover.ts`, together with `useHoverPopover<T>()` —
  the hover state machine both palette surfaces use — and `computeTileAnchor`,
  which opens the card to the right of the tile and clamps its top into the
  viewport. The canvas keeps its own anchor (`computeNodeDetailAnchor`, §10)
  because a placed node can sit anywhere and the viewport pans and zooms.
- Interactivity is opt-in per call site: a surface spreads
  `useHoverPopover().popoverProps`, which supplies the `interactive` flag
  together with the handlers that keep the card open. The two must arrive
  together, because a card that swallows pointer events without maintaining
  hover state closes under the cursor. The canvas node popover (§10) spreads
  nothing and stays display-only and `pointer-events-none`, unchanged.
- `BlockDetailPopover` takes an `actions` slot rendered under the port
  signature, above a hairline rule (testid `palette-popover-actions`). That is
  where "Promote to My Library" mounts.
- Each palette surface passes `actions` **only when the hovered item is
  promotable** (ADR-053 FR-019: resolved origin `project`). FR-019's "hidden,
  not shown disabled" covers the hairline-ruled row itself — handing the card an
  element that rendered nothing would leave an empty ruled-off strip under every
  built-in, packaged, and already-promoted tile — so a non-promotable item's
  card stays byte-identical to the pre-ADR-053 one.

Tile dragging is unaffected: `handleDragStart` closes the card immediately
rather than through the grace period, and the drag payload contract is
unchanged (ADR-053 FR-045).

## 7. Out Of Scope

- The original #1797 redesign made no backend, schema, or `BlockSummary`
  contract change. The ADR-053 tier split adds exactly one optional field,
  `BlockSummary.origin` (FR-004), which §4.1 consumes; nothing else about the
  contract moved.
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
- Origin resolution: the backend value passes through, an unrecognised value is
  treated as absent, and a payload without one falls back to the legacy
  `source` label.
- Origin-first grouping: user → My Library, project and the `custom` fallback →
  This Project, builtin/package → `derivePackage`; Data I/O outranks all of it.
- Section ordering: Data I/O → Built-in → My Library → This Project → plugin
  packages A→Z, each section sorted by block name.
- Data I/O lifted out of its group (no duplicate rendering).
- Both tier sections render empty with their teaching copy, and drop it while a
  filter is active.
- Category-chip filter composes with text search (AND), across the tier
  sections exactly as across the package sections.

The generic half is covered by `palette/__tests__/sections.test.ts`, exercised
against an item type that is neither a block nor a type so the FR-047 claim
that one skeleton fits both surfaces stays honest, and by
`palette/__tests__/useHoverPopover.test.tsx` (open delay, close grace, anchor
clamping, re-targeting between tiles, no timer left after unmount).

Component behavior is covered by the rewritten `BlockPalette.test.tsx`:

- Grid tiles render the category icon/swatch and the block name (no always-on
  description, no `in / out` text line).
- Data I/O section renders Load and Save pinned at the top.
- Activating a category chip filters the visible tiles.
- Hovering a tile reveals the detail popover with description and port signature.
- The panel is titled `Blocks`; `My Library` and `This Project` replace `Custom`
  and render with their teaching copy when empty.
- The popover carries no `pointer-events-none`, survives the tile→popover gap,
  closes when the pointer leaves the card, and does not disturb dragging.

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
- **Portalled outside ReactFlow.** The popover is rendered through a React
  portal to `document.body`, not inline in the node subtree. ReactFlow's
  viewport applies a CSS `transform`, which makes it the containing block for a
  `position: fixed` descendant; rendering the popover inside it would place the
  card in the transformed coordinate space and drift it from the node after
  pan/zoom. Portalling to `<body>` restores the real viewport coordinate space
  that the `getBoundingClientRect()`-derived anchor is expressed in.
- **Coexistence.** The detail popover floats to the side of the 104×104 square;
  the existing `NodeActionToolbar` floats above it (ADR-050 §2.2). They do not
  overlap and both may be visible on hover.
- **Graceful no-op.** When `data.summary` is absent (e.g. an unresolved
  custom/plugin block), no popover opens.

## 11. Data Types Tab (ADR-053 §9.2 Amendment)

The left panel gains a third tab, **Data types**, between Blocks and Project
(ADR-053 FR-039). The label is `Data types` rather than `Types`, which is too
abstract standing alone next to `Blocks`; the internal `leftTab` key stays
`types`. `frontend/src/components/TypePalette.tsx` is the pane, with its
`TypePalette.parts/` model, tile, and popover siblings.

### 11.1 It Mirrors The Blocks Tab, Reusing Its Machinery

The tab reuses §4.3's shared skeleton rather than restating it: `filterItems`
and `buildSections<T>` build the sections, `PaletteTile` is the grid cell,
`FilterChips` is the chip row, `useHoverPopover` is the hover state machine,
and `DetailPopover` is the card. The type side supplies only its four
callbacks — group, sort, haystack, facet — which is ADR-053 FR-047's claim that
one skeleton fits both surfaces with no per-surface special-casing. Per
ADR-053 §10.2 nothing block-side is reused (`derivePackage`, the io
source/sink predicates, `CATEGORY_KEYS`, `portSignature` stay block concepts)
and nothing type-side is generalised into the block model.

Section order (FR-040): **Core** (pinned, never collapses) → **My Library** →
**This Project** → one section per package, A→Z. My Library and This Project
render even when empty, each carrying one line stating what the section is for,
on the same terms as §4.2 — and, as there, the teaching copy is dropped while a
filter is active. The FR-002 `custom` fallback files under This Project for the
same reason it does on the Blocks tab.

A package section is titled by `TypeSummary.package_name`, which the listing
reports as **the same string** `BlockSummary.package_name` carries for that
distribution rather than as a second name derived to resemble it. Inferring a
distribution name from `file_path` was rejected and stays rejected: it would
produce a section title the backend never supplied, and one that could disagree
with the Blocks tab's real name for the same distribution, which is the drift
ADR-053 exists to remove. Instead the type registry records which
distribution's discovery hook delivered each type (`TypeSpec.package_root`) and
the listing looks the display name up in the block registry, so the two tabs
cannot spell one package two ways. A package-tier type the backend cannot name
reports `null` and collects in a lumped `Packages` section — the
pre-attribution behaviour, kept so a type can never vanish because its
distribution went unnamed. That id and every real package name land in the same
A→Z remainder, which is where FR-040 puts packages: after both tier sections.

The search input matches name, description, base type, **and** registered
extensions, so typing `.csv` answers "which type do I get if I load a CSV?".
The chip vocabulary is surface-owned (ADR-053 §10.1): the Blocks tab filters by
base category, the Data types tab filters by the **core base family** a type
descends from (`Array`, `DataFrame`, `Series`, …), resolved with the existing
`resolveCoreBaseType`. Each chip is tinted with that family's own resolved
colour, so the chip row doubles as a legend for the tile swatches.

The tab reads the type catalogue directly rather than taking it as a prop
(ADR-053 FR-027): opening it neither waits for nor re-triggers a blocks fetch,
and its Reload re-fetches only types, blinking with the same `useReloadFlash`
hook the Blocks tab and the project tree use.

### 11.2 Tile And Popover

Each tile is a `PaletteTile` carrying the **canvas port colour** — solid fill
plus ring, with `border = ring ?? fill` — lifted verbatim from the port handles
rather than restated, so a type reads identically in the palette and on a
canvas port (ADR-053 FR-041). No new colour table is introduced. Type tiles are
not draggable; click or keyboard activation opens the same detail card hovering
does, anchored to the tile, so the card and the action inside it are reachable
without a pointer.

The popover is the §6 shared card composed with type content (testid
`type-detail-popover`), carrying: name and swatch in the header; the immediate
parent, plus the core base type when the two differ (FR-043 — `resolveCoreBaseType`
returns `null` when the type already is a core base, so no redundant
`Array (Array)` is rendered, and the row is omitted for `DataObject`, which has
no parent); the docstring description; loadable-from and saveable-to extensions
reported **separately**, an empty direction rendering as an em dash so a
save-only type reads as save-only (FR-055), or one explicit
`No file formats registered` line when the type has neither (FR-056); and the
origin tier. The `actions` slot (testid `palette-popover-actions`, §6.1) is
where **Promote to My Library** mounts, exactly as on the block card — and, as
on the block card, the tab supplies that slot only for a type whose origin is
`project`, so a core, packaged, or already-promoted type's card carries no
action row at all.

### 11.3 Canvas Port Colour Changes Source (ADR-053 FR-066, FR-067)

Canvas port and edge colour previously resolved entirely frontend-side, with
`type_hierarchy` supplying `base_type`. A type can now declare its own colour,
and that declaration arrives on the types listing — which becomes the **single
source of type colour** for the product. `type_hierarchy` keeps serving type
hierarchy and stops being a colour transport; its long-dead `ui_ring_color`
field stays dead and is no longer read, because two supply points for one fact
are the drift being removed.

Resolution precedence, identical for palette tiles and canvas ports (FR-051):

1. the colour the type declared, from the types listing,
2. the existing `typeColorMap` entry — directly or via `base_type`,
3. the `hashTypeName` fallback.

An undeclared type therefore resolves byte-identically to before. A malformed
declaration is warned once and falls through to the next level (FR-052); the
warning is de-duplicated because ports re-resolve colour on every render.

Colour and block data used to arrive in one response and so could never
disagree or arrive out of order; they are now two. The window between them is
handled by not having one: the declared-colour lookup is `undefined` until a
complete listing lands, the resolvers read `undefined` exactly as they read
"declares nothing", and ports render the pre-ADR-053 colour meanwhile. Nothing
re-layouts when the listing arrives — colour is paint-only, port Y comes from
`portRailOffset` — and for a type that declares nothing the two answers are the
same string, so there is nothing to see. That is FR-067, and it is covered by
`components/__tests__/typeColorSource.test.tsx`, which renders a palette tile
and a canvas port together and asserts they agree before and after the listing
lands.

### 11.4 Test Plan

Pure model rules live in `TypePalette.parts/typeModel.ts` and are covered by
`TypePalette.parts/__tests__/typeModel.test.ts`: origin-tier grouping including
the `custom` fallback, section order, both tier empty states and their
suppression under a filter, search across name/description/base/extensions,
chip composition, family resolution, the parent chain, and the separate
load/save extension rows including the no-formats case.

Component behaviour is covered by `components/__tests__/TypePalette.test.tsx`:
the panel title and tab structure, tier sections and teaching copy, search and
chip filtering, tile colour under the precedence, every popover row, popover
interactivity across the tile→card gap, self-fetching, and Reload.

Cross-surface colour behaviour is covered by
`components/__tests__/typeColorSource.test.tsx` (FR-066 parity, the FR-067
loading window and its no-flash / no-re-layout assertions, FR-052 fall-through)
and by `config/__tests__/typeColorMap.test.ts` for the pure precedence,
normalisation, and warning de-duplication.
