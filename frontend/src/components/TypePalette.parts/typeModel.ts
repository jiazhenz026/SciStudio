// Pure Data types tab model — tier grouping, ordering, filtering, facets, and
// the popover's derived rows. Kept free of React/JSX so every rule below is
// unit-testable in isolation, exactly as `BlockPalette.parts/paletteModel.ts`
// is on the block side.
//
// The generic half (`Section`, `buildSections`, `filterItems`,
// `withoutEmptyHints`) lives in `components/palette/sections.ts` and is shared
// with the Blocks tab. Both surfaces group primarily by origin tier, so one
// skeleton fits both with no per-surface special-casing (FR-047) — this module
// supplies only the type-side callbacks it takes.
//
// Per spec §10.2 nothing here is reused from the block side and nothing here
// is generalised into it: `derivePackage`, the io source/sink predicates,
// `CATEGORY_KEYS` and `portSignature` are block concepts, and the tier ids,
// the type family facet, and the extension rows below are type concepts.
//
// Specs:
//   docs/specs/adr-053-personal-tool-library.md §9.2 (FR-039 – FR-043),
//     §7.2 (FR-054 – FR-056), §10.1 (FR-047), §10.2.
//   docs/specs/frontend-block-palette.md §11 (Data types tab).

import { resolveCoreBaseType } from "../../config/typeColorMap";
import type { Section, SectionSlot } from "../palette/sections";
import { buildSections, filterItems, withoutEmptyHints } from "../palette/sections";
import type { TypeHierarchyEntry, TypeSummary } from "../../types/api";

/** A Data types tab section — the type specialisation of the shared model. */
export type TypeSection = Section<TypeSummary>;

/** Stable id for the pinned core section (`scistudio.core.types`). */
export const CORE_SECTION_ID = "__core__";
/** Stable id for the user-wide library section (`~/.scistudio/types/`). */
export const USER_LIBRARY_SECTION_ID = "__user_library__";
/** Stable id for the project-local section (`{project}/types/`). */
export const PROJECT_LIBRARY_SECTION_ID = "__this_project__";
/**
 * Fallback section for a package-tier type whose distribution has no name.
 *
 * A package section is titled by its `package_name`, which the backend reports
 * as the very string `BlockSummary.package_name` carries for the same
 * distribution (FR-040) — never inferred from `file_path`, because a name that
 * disagreed with the Blocks tab's would be exactly the drift this spec exists
 * to remove. When the backend cannot name a distribution it says `null` rather
 * than guessing, and those types collect here instead of vanishing. Both this
 * id and every real package name land in the same A→Z remainder, which is
 * where FR-040 puts packages: after the two tier sections.
 */
export const PACKAGES_SECTION_ID = "Packages";

/**
 * The section a type belongs to — its origin tier, then its package (FR-005,
 * FR-040), which is the order the Blocks tab resolves in too.
 *
 * `custom` is the FR-002 fallback for a drop-in whose `file_path` resolved
 * under neither tier root. It renders under **This Project** for the same
 * reason it does on the Blocks tab: an unresolvable drop-in is not known to be
 * reusable across projects, so filing it under a section that promises
 * cross-project reuse would be a claim the backend did not make — and This
 * Project renders unconditionally (FR-037), so such a type can never silently
 * vanish from the palette.
 */
export function typeSectionIdFor(type: TypeSummary): string {
  switch (type.origin) {
    case "core":
      return CORE_SECTION_ID;
    case "user":
      return USER_LIBRARY_SECTION_ID;
    case "project":
    case "custom":
      return PROJECT_LIBRARY_SECTION_ID;
    default:
      return type.package_name || PACKAGES_SECTION_ID;
  }
}

/**
 * FR-037 teaching copy, the type-side counterpart of the block hints. Same
 * job: for a user who has never heard of a personal library, the empty section
 * is the only moment they are guaranteed to be looking at the place it would
 * live, so these lines are load-bearing product copy rather than filler.
 */
export const MY_LIBRARY_EMPTY_HINT =
  "No data types of your own yet. Save a type here and every project can use it.";
export const THIS_PROJECT_EMPTY_HINT =
  "No data types in this project yet. Types you add here stay with this project.";

/**
 * The ordered head of the type section list (FR-040).
 *
 * Core is pinned at the top — it is the vocabulary every workflow is built
 * from and it never collapses. `My Library` then sits above `This Project` for
 * the same reason as on the Blocks tab (FR-036): it is the container the
 * product is asking users to invest in, and ordering it last would state the
 * opposite. Both carry an `emptyHint`, so both render even when empty
 * (FR-037); Core and the Packages remainder keep the ordinary
 * omit-when-empty behaviour.
 */
export const TYPE_SECTION_SLOTS: readonly SectionSlot[] = [
  { id: CORE_SECTION_ID, title: "Core", pinned: true },
  { id: USER_LIBRARY_SECTION_ID, title: "My Library", emptyHint: MY_LIBRARY_EMPTY_HINT },
  { id: PROJECT_LIBRARY_SECTION_ID, title: "This Project", emptyHint: THIS_PROJECT_EMPTY_HINT },
];

/** Human label for an origin tier, used in the popover's Origin row (FR-042). */
export function originLabel(origin: TypeSummary["origin"]): string {
  switch (origin) {
    case "core":
      return "Core";
    case "user":
      return "My Library";
    case "project":
      return "This Project";
    case "package":
      return "Package";
    default:
      return "Custom";
  }
}

/**
 * View the types listing as a `type_hierarchy` (a `name → base_type` map).
 *
 * `resolveCoreBaseType` walks that shape, and reusing it rather than writing a
 * second traversal is FR-043's explicit instruction. FR-027 is why the listing
 * supplies the shape here instead of the tab reading `type_hierarchy` off a
 * block schema: the Data types tab must not have to fetch blocks to draw
 * types.
 */
export function typeHierarchyFrom(types: readonly TypeSummary[]): TypeHierarchyEntry[] {
  return types.map((type) => ({
    name: type.name,
    base_type: type.base_type,
    description: type.description,
  }));
}

/**
 * The core base family a type belongs to, or `null` when it has none.
 *
 * This is the type-side facet vocabulary (§10.1 keeps the chip vocabulary
 * surface-owned): the Blocks tab filters by base category, the Data types tab
 * filters by the family a type descends from, so "show me everything that is
 * an Array" is one click. A core base is its own family; `DataObject` and any
 * type whose chain does not resolve have none.
 */
export function typeFamily(
  type: TypeSummary,
  hierarchy: readonly TypeHierarchyEntry[],
): string | null {
  if (type.name === "DataObject") {
    return null;
  }
  const core = resolveCoreBaseType(type.name, hierarchy as TypeHierarchyEntry[]);
  if (core) {
    return core;
  }
  // `resolveCoreBaseType` returns null for a type that already IS a core base
  // (no redundant `Array (Array)`), so read that case off `base_type` here.
  return type.base_type === "DataObject" ? type.name : null;
}

/** The distinct families present in `types`, A→Z — the chip vocabulary. */
export function typeFamilies(types: readonly TypeSummary[]): string[] {
  const hierarchy = typeHierarchyFrom(types);
  const families = new Set<string>();
  for (const type of types) {
    const family = typeFamily(type, hierarchy);
    if (family) {
      families.add(family);
    }
  }
  return [...families].sort((a, b) => a.localeCompare(b));
}

/**
 * Text a type is searched by.
 *
 * Extensions are included deliberately: "which type do I get if I load a
 * `.csv`?" is a question the listing can now answer (§7.2), and searching
 * `.csv` is the shortest path to it.
 */
function typeHaystack(type: TypeSummary): string {
  return `${type.name} ${type.description} ${type.base_type} ${type.load_extensions.join(" ")} ${type.save_extensions.join(" ")}`;
}

/** Apply text search AND the family-chip filter (both must pass). */
export function filterTypes(
  types: readonly TypeSummary[],
  search: string,
  activeFamilies: readonly string[],
): TypeSummary[] {
  const searched = filterItems(types, search, typeHaystack);
  const active = new Set(activeFamilies);
  if (active.size === 0) {
    return searched;
  }
  const hierarchy = typeHierarchyFrom(types);
  return searched.filter((type) => {
    const family = typeFamily(type, hierarchy);
    return family !== null && active.has(family);
  });
}

/** True when a search term or at least one family chip is narrowing the grid. */
export function isFilteringTypes(search: string, activeFamilies: readonly string[]): boolean {
  return search.trim().length > 0 || activeFamilies.length > 0;
}

const byName = (a: TypeSummary, b: TypeSummary): number => a.name.localeCompare(b.name);

/**
 * Build the ordered Data types sections from the visible types.
 *
 * Order (FR-040): Core (pinned) → My Library → This Project → one section per
 * package, A→Z by name, exactly as the Blocks tab orders its own. The A→Z half
 * is `buildSections`' remainder behaviour rather than a second ordering pass.
 * My Library and This Project also render empty (FR-037) — except while a
 * filter is active, where an empty section says nothing about the library and
 * everything about the query.
 */
export function buildTypeSections(
  types: readonly TypeSummary[],
  search: string,
  activeFamilies: readonly string[],
): TypeSection[] {
  const visible = filterTypes(types, search, activeFamilies);
  const slots = isFilteringTypes(search, activeFamilies)
    ? withoutEmptyHints(TYPE_SECTION_SLOTS)
    : TYPE_SECTION_SLOTS;
  return buildSections(visible, typeSectionIdFor, slots, byName);
}

/** One direction of the popover's Extensions row (FR-054, FR-055). */
export interface ExtensionRow {
  label: "Load" | "Save";
  /** Extensions, or `null` when this direction has none registered. */
  extensions: string[] | null;
}

/**
 * The popover's extension rows, or `null` when the type has no format
 * capability at all.
 *
 * FR-055 keeps the two directions separate — a type readable from a format it
 * cannot be written back to is a real and useful asymmetry, and a type that
 * can only be saved renders `Load —` rather than hiding the fact. FR-056 turns
 * the both-empty case into one explicit statement instead of a silent gap,
 * which is what `null` signals to the caller.
 */
export function extensionRows(type: TypeSummary): ExtensionRow[] | null {
  const load = type.load_extensions ?? [];
  const save = type.save_extensions ?? [];
  if (load.length === 0 && save.length === 0) {
    return null;
  }
  return [
    { label: "Load", extensions: load.length > 0 ? load : null },
    { label: "Save", extensions: save.length > 0 ? save : null },
  ];
}

/** FR-056 copy for a type no format capability mentions. */
export const NO_FORMATS_TEXT = "No file formats registered";

/**
 * The popover's Parent row: the immediate base class, plus the core base type
 * when the two differ (FR-042, FR-043).
 *
 * `resolveCoreBaseType` returns `null` when the type already IS a core base,
 * so nothing here renders a redundant `Array (Array)`. Returns `null` for a
 * type with no parent — `DataObject` itself — where a "Parent: none" row would
 * be noise rather than information.
 */
export function parentRow(
  type: TypeSummary,
  hierarchy: readonly TypeHierarchyEntry[],
): { parent: string; coreBase: string | null } | null {
  if (!type.base_type) {
    return null;
  }
  const coreBase = resolveCoreBaseType(type.name, hierarchy as TypeHierarchyEntry[]);
  return {
    parent: type.base_type,
    coreBase: coreBase && coreBase !== type.base_type ? coreBase : null,
  };
}

/**
 * The parent shown on a list row (FR-041), or `null` when it carries no
 * information.
 *
 * `DataObject` is the universal root — `resolveCoreBaseType` stops there, and
 * `typeFamilyOf` above reads `base_type === "DataObject"` as "this type is its
 * own family" — so printing it beside every core base type would be the row's
 * version of the redundant `Array (Array)` that FR-043 keeps out of the
 * popover. The popover still reports the full chain; the row is an index, and
 * an index that repeats one word down its whole right edge indexes nothing.
 */
export function rowParent(type: TypeSummary): string | null {
  if (!type.base_type || type.base_type === "DataObject") {
    return null;
  }
  return type.base_type;
}

/** Which tier's file-open path reaches a type's source, and under what name. */
export interface TypeSourceRef {
  tier: "project" | "user";
  /** Bare filename inside that tier's `types/` directory. */
  filename: string;
}

/**
 * FR-068 — where this type's source can be opened from, or `null`.
 *
 * Only the two drop-in tiers qualify, and for a reason rather than by
 * omission: a core or packaged type's file lives inside an installed
 * distribution, which neither file-open path can reach and which the user must
 * not be invited to edit in place. There is no read-only viewer for those yet
 * (`openBlockSourceTab`'s type-side counterpart does not exist), so a row for
 * one opens nothing at all rather than opening something wrong.
 *
 * The filename is derived from the listing's absolute `file_path` the same way
 * `promotion/promotable.ts` derives it: both drop-in tiers put a type directly
 * in a `types/` directory by construction (`scistudio.core.dropins`), so the
 * basename is the whole of what either opener needs.
 */
export function typeSourceRef(type: TypeSummary): TypeSourceRef | null {
  if (type.origin !== "project" && type.origin !== "user") {
    return null;
  }
  const filename = type.file_path ? (type.file_path.split(/[\\/]/).pop() ?? "") : "";
  if (!filename.toLowerCase().endsWith(".py")) {
    return null;
  }
  return { tier: type.origin, filename };
}
