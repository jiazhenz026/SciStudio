// Pure palette model — ordering, Load/Save detection, filtering, and port
// signatures for the BlockPalette grid. Kept free of React/JSX so the ordering
// and detection rules are unit-testable in isolation.
//
// Spec: docs/specs/frontend-block-palette.md
//   §4 Sections And Ordering, §5 Category Filter, §6 Hover Detail.

import { primaryTypeName } from "../../config/typeColorMap";
import type { BlockPortResponse, BlockSummary } from "../../types/api";

/** Base categories shown as filter chips, in display order. */
export const CATEGORY_KEYS = ["io", "process", "code", "app", "ai"] as const;
export type CategoryKey = (typeof CATEGORY_KEYS)[number];

/** Stable id for the pinned Data I/O section (not a real package name). */
export const DATA_IO_SECTION_ID = "__data_io__";
/** Package name the core built-in blocks resolve to via `derivePackage`. */
export const BUILTIN_PACKAGE = "SciStudio Core";
/** Package name custom user blocks resolve to. */
export const CUSTOM_PACKAGE = "Custom";

/**
 * Dotted type_name namespaces that ship with core and must be treated as
 * Built-in rather than as a standalone plugin package. The core AI block
 * (`ai.agent`) uses the `ai.` namespace but is not a decoupled plugin, so it
 * belongs under Built-in. Real plugins (imaging / lcms / spectroscopy / srs)
 * are not listed here.
 */
const CORE_NAMESPACES = new Set(["ai"]);

export interface PaletteSection {
  /** Stable key for React + collapse state. */
  id: string;
  /** Header label shown to the user. */
  title: string;
  blocks: BlockSummary[];
  /** Pinned sections (Data I/O) always render and never collapse. */
  pinned: boolean;
}

/**
 * Derive the display package name for a block.
 *
 * Priority:
 *   1. block.package_name (explicit backend field)
 *   2. "Custom" for blocks with source === "custom"
 *   3. prefix before the first dot in type_name (e.g. "Imaging" from
 *      "imaging.cellpose_segment"); short prefixes (≤4 chars) are uppercased.
 *   4. "SciStudio Core" for builtin blocks / no dot in type_name
 */
export function derivePackage(block: BlockSummary): string {
  if (block.package_name) {
    return block.package_name;
  }
  if (block.source === "custom") {
    return CUSTOM_PACKAGE;
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

function matchesSearch(block: BlockSummary, search: string): boolean {
  if (!search) {
    return true;
  }
  const haystack =
    `${block.name} ${block.description} ${block.subcategory || block.base_category}`.toLowerCase();
  return haystack.includes(search.toLowerCase());
}

function matchesCategory(block: BlockSummary, active: ReadonlySet<string>): boolean {
  return active.size === 0 || active.has(block.base_category);
}

/** Apply text search AND category-chip filter (both must pass). */
export function filterBlocks(
  blocks: BlockSummary[],
  search: string,
  activeCategories: readonly string[],
): BlockSummary[] {
  const active = new Set(activeCategories);
  return blocks.filter((block) => matchesSearch(block, search) && matchesCategory(block, active));
}

const byName = (a: BlockSummary, b: BlockSummary): number => a.name.localeCompare(b.name);

/**
 * Build the ordered palette sections from the visible blocks.
 *
 * Order (spec §4): Data I/O (pinned) → Built-in (core) → Custom → plugin
 * packages A→Z. Data I/O blocks are lifted out of their package group so they
 * never render twice. Empty sections are omitted.
 */
export function buildPaletteSections(
  blocks: BlockSummary[],
  search: string,
  activeCategories: readonly string[],
): PaletteSection[] {
  const visible = filterBlocks(blocks, search, activeCategories);

  const dataIo = visible.filter(isDataIoBlock).sort(byName);
  const rest = visible.filter((block) => !isDataIoBlock(block));

  const packageMap = new Map<string, BlockSummary[]>();
  for (const block of rest) {
    const pkg = derivePackage(block);
    if (!packageMap.has(pkg)) {
      packageMap.set(pkg, []);
    }
    packageMap.get(pkg)!.push(block);
  }

  const sections: PaletteSection[] = [];

  if (dataIo.length > 0) {
    sections.push({ id: DATA_IO_SECTION_ID, title: "Data I/O", blocks: dataIo, pinned: true });
  }

  const takeSection = (pkg: string, title: string): void => {
    const pkgBlocks = packageMap.get(pkg);
    if (pkgBlocks && pkgBlocks.length > 0) {
      sections.push({ id: pkg, title, blocks: [...pkgBlocks].sort(byName), pinned: false });
    }
    packageMap.delete(pkg);
  };

  takeSection(BUILTIN_PACKAGE, "Built-in");
  takeSection(CUSTOM_PACKAGE, CUSTOM_PACKAGE);

  for (const pkg of [...packageMap.keys()].sort((a, b) => a.localeCompare(b))) {
    sections.push({
      id: pkg,
      title: pkg,
      blocks: [...packageMap.get(pkg)!].sort(byName),
      pinned: false,
    });
  }

  return sections;
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
