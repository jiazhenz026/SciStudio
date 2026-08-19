// Pure palette model — ordering, Load/Save detection, filtering, and port
// signatures for the BlockPalette grid. Kept free of React/JSX so the ordering
// and detection rules are unit-testable in isolation.
//
// The generic half (Section, buildSections, filterItems) lives in
// `components/palette/sections.ts` and is shared with the Data types tab; this
// module is the block-side specialisation. Per spec §10.2 `derivePackage`, the
// io source/sink predicates, `CATEGORY_KEYS` and `portSignature` stay here —
// they are block concepts and must not be generalised.
//
// Specs:
//   docs/specs/frontend-block-palette.md §4 Sections And Ordering,
//     §5 Category Filter, §6 Hover Detail.
//   docs/specs/adr-053-personal-tool-library.md §9.1 (FR-034 – FR-038),
//     §10.1 (FR-047), §10.2.

import {
  buildSections,
  filterItems,
  withoutEmptyHints,
  type Section,
  type SectionSlot,
} from "../palette/sections";
import { primaryTypeName } from "../../config/typeColorMap";
import type { BlockOrigin, BlockPortResponse, BlockSummary } from "../../types/api";

/** Base categories shown as filter chips, in display order. */
export const CATEGORY_KEYS = ["io", "process", "code", "app", "ai"] as const;
export type CategoryKey = (typeof CATEGORY_KEYS)[number];

/** Stable id for the pinned Data I/O section (not a real package name). */
export const DATA_IO_SECTION_ID = "__data_io__";
/** Stable id for the user-wide library section (`~/.scistudio/blocks/`). */
export const USER_LIBRARY_SECTION_ID = "__user_library__";
/** Stable id for the project-local section (`{project}/blocks/`). */
export const PROJECT_LIBRARY_SECTION_ID = "__this_project__";
/** Package name the core built-in blocks resolve to via `derivePackage`. */
export const BUILTIN_PACKAGE = "SciStudio Core";

/**
 * Dotted type_name namespaces that ship with core and must be treated as
 * Built-in rather than as a standalone plugin package. The core AI block
 * (`ai.agent`) uses the `ai.` namespace but is not a decoupled plugin, so it
 * belongs under Built-in. Real plugins (imaging / lcms / spectroscopy / srs)
 * are not listed here.
 */
const CORE_NAMESPACES = new Set(["ai"]);

/** A block palette section — the block specialisation of the shared model. */
export type PaletteSection = Section<BlockSummary>;

/**
 * The block origin vocabulary as it arrives on the block list response
 * (ADR-053 FR-001 / FR-002 / FR-004). Declared as a typed array so the runtime
 * membership test below cannot drift from the union in `types/api.ts`.
 */
const BLOCK_ORIGIN_VALUES: readonly BlockOrigin[] = [
  "builtin",
  "user",
  "project",
  "package",
  "custom",
];

/**
 * Resolve the tier a block came from.
 *
 * The backend sends `origin` (FR-004). A payload without a recognised origin —
 * an older backend, or a field the frontend does not know — falls back to the
 * pre-ADR-053 `source` label, which collapsed both tier-1 directories into
 * `custom`. Anything else takes the package family, where `derivePackage`
 * performs the core-vs-plugin split exactly as it does today; that keeps
 * `builtin` and plugin rendering byte-identical to current behaviour whether
 * or not the backend has been upgraded.
 */
export function resolveBlockOrigin(block: BlockSummary): BlockOrigin {
  const declared = block.origin;
  if (declared !== undefined && BLOCK_ORIGIN_VALUES.includes(declared)) {
    return declared;
  }
  return block.source === "custom" ? "custom" : "package";
}

/**
 * Derive the display package name for a block.
 *
 * Priority:
 *   1. block.package_name (explicit backend field)
 *   2. prefix before the first dot in type_name (e.g. "Imaging" from
 *      "imaging.cellpose_segment"); short prefixes (≤4 chars) are uppercased.
 *   3. "SciStudio Core" for builtin blocks / no dot in type_name
 *
 * Tier-1 blocks never reach a package section (FR-038 routes them by origin
 * before package), so this no longer needs a "Custom" branch.
 */
export function derivePackage(block: BlockSummary): string {
  if (block.package_name) {
    return block.package_name;
  }
  const dotIndex = block.type_name.indexOf(".");
  if (dotIndex > 0) {
    const prefix = block.type_name.slice(0, dotIndex);
    if (CORE_NAMESPACES.has(prefix)) {
      return BUILTIN_PACKAGE;
    }
    if (prefix.length <= 4) {
      return prefix.toUpperCase();
    }
    return prefix.charAt(0).toUpperCase() + prefix.slice(1);
  }
  return BUILTIN_PACKAGE;
}

/** io source (e.g. Load) — an io block that consumes nothing. */
export function isIoSource(block: BlockSummary): boolean {
  return block.base_category === "io" && block.input_ports.length === 0;
}

/** io sink (e.g. Save) — an io block that produces nothing. */
export function isIoSink(block: BlockSummary): boolean {
  return block.base_category === "io" && block.output_ports.length === 0;
}

/** Load/Save blocks pinned to the top Data I/O section. */
export function isDataIoBlock(block: BlockSummary): boolean {
  return isIoSource(block) || isIoSink(block);
}

/**
 * The section a block belongs to — origin tier first, package second (FR-038).
 *
 * The pinned Data I/O group wins over everything: it is a cross-tier lift of
 * the two core io endpoints and predates the tier split.
 *
 * `custom` is the FR-002 fallback for a tier-1 block whose `file_path` could
 * not be resolved to either root (absent path, symlink escaping both, differing
 * Windows drive). It renders under **This Project** rather than under My
 * Library: an unresolvable drop-in is not known to be reusable across projects,
 * so filing it under a section that promises cross-project reuse would be a
 * claim the backend did not make. This Project is also the section that renders
 * unconditionally (FR-037), so a `custom` block can never silently vanish from
 * the palette. It is the same bucket every tier-1 block lands in on a backend
 * that has not yet split the tiers, which keeps today's single `Custom` section
 * mapping onto the closer of the two new ones.
 */
export function sectionIdFor(block: BlockSummary): string {
  if (isDataIoBlock(block)) {
    return DATA_IO_SECTION_ID;
  }
  switch (resolveBlockOrigin(block)) {
    case "user":
      return USER_LIBRARY_SECTION_ID;
    case "project":
    case "custom":
      return PROJECT_LIBRARY_SECTION_ID;
    default:
      return derivePackage(block);
  }
}

/**
 * FR-037 teaching copy. These lines are the cheapest discovery surface in the
 * whole feature — for a user who has never heard of a personal library, the
 * empty section is the only moment they are guaranteed to be looking at the
 * place it would live — so they are load-bearing product copy, not filler.
 */
export const MY_LIBRARY_EMPTY_HINT =
  "No blocks of your own yet. Save a block here and every project can use it.";
export const THIS_PROJECT_EMPTY_HINT =
  "No blocks in this project yet. Blocks you add here stay with this project.";

/**
 * The ordered head of the block section list (FR-036).
 *
 * `My Library` sits above `This Project` because it is the container the
 * product is asking users to invest in; ordering it last would state the
 * opposite. Both carry an `emptyHint`, so both render even when empty
 * (FR-037); Data I/O and Built-in keep the ordinary omit-when-empty behaviour,
 * as do the plugin package sections in the A→Z remainder.
 */
export const BLOCK_SECTION_SLOTS: readonly SectionSlot[] = [
  { id: DATA_IO_SECTION_ID, title: "Data I/O", pinned: true },
  { id: BUILTIN_PACKAGE, title: "Built-in" },
  { id: USER_LIBRARY_SECTION_ID, title: "My Library", emptyHint: MY_LIBRARY_EMPTY_HINT },
  { id: PROJECT_LIBRARY_SECTION_ID, title: "This Project", emptyHint: THIS_PROJECT_EMPTY_HINT },
];

/** Text a block is searched by. */
function blockHaystack(block: BlockSummary): string {
  return `${block.name} ${block.description} ${block.subcategory || block.base_category}`;
}

/** Apply text search AND category-chip filter (both must pass). */
export function filterBlocks(
  blocks: BlockSummary[],
  search: string,
  activeCategories: readonly string[],
): BlockSummary[] {
  const searched = filterItems(blocks, search, blockHaystack);
  const active = new Set(activeCategories);
  return active.size === 0 ? searched : searched.filter((b) => active.has(b.base_category));
}

/** True when a search term or at least one category chip is narrowing the grid. */
export function isFiltering(search: string, activeCategories: readonly string[]): boolean {
  return search.trim().length > 0 || activeCategories.length > 0;
}

const byName = (a: BlockSummary, b: BlockSummary): number => a.name.localeCompare(b.name);

/**
 * Build the ordered palette sections from the visible blocks.
 *
 * Order (FR-036): Data I/O (pinned) → Built-in → My Library → This Project →
 * plugin packages A→Z. Data I/O blocks are lifted out of their tier group so
 * they never render twice. My Library and This Project also render empty
 * (FR-037) — except while a filter is active, where an empty section says
 * nothing about the library and everything about the query.
 */
export function buildPaletteSections(
  blocks: BlockSummary[],
  search: string,
  activeCategories: readonly string[],
): PaletteSection[] {
  const visible = filterBlocks(blocks, search, activeCategories);
  const slots = isFiltering(search, activeCategories)
    ? withoutEmptyHints(BLOCK_SECTION_SLOTS)
    : BLOCK_SECTION_SLOTS;
  return buildSections(visible, sectionIdFor, slots, byName);
}

export interface PortSignatureEntry {
  name: string;
  /** Primary accepted type name, or "Any" when untyped. */
  type: string;
}

/** Build `name : Type` port rows for the hover detail popover (spec §6). */
export function portSignature(ports: BlockPortResponse[]): PortSignatureEntry[] {
  return ports.map((port) => ({
    name: port.name,
    type: primaryTypeName(port.accepted_types ?? []),
  }));
}
