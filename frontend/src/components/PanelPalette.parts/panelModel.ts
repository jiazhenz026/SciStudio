// Pure Panels tab model — tier grouping, ordering, filtering, and the
// per-type choice lookups. Kept free of React/JSX so every rule below is
// unit-testable in isolation, exactly as `TypePalette.parts/typeModel.ts` is
// on the type side.
//
// The generic half (`Section`, `buildSections`, `filterItems`,
// `withoutEmptyHints`) lives in `components/palette/sections.ts` and is shared
// with the Blocks and Data types tabs (ADR-053 §10.1, FR-047).
//
// The section order follows the palette skeleton both sibling tabs use
// (ADR-053 §10.1, FR-047): This Project → My Library → Core, then packages as
// the A→Z remainder. The FR-003 routing precedence the backend orders its
// listing by (#2095) is preserved inside each card's tier label rather than in
// the section order, so all three left-panel catalogues read identically.
//
// Specs:
//   docs/specs/adr-048-preview-system.md FR-003 (precedence), FR-031..FR-033
//     (discovery + reload), FR-034..FR-038 (the per-type choice).
//   docs/specs/frontend-block-palette.md §12 (this tab).

import { buildSections, filterItems, withoutEmptyHints } from "../palette/sections";
import type { Section, SectionSlot } from "../palette/sections";
import type { PanelChoice, PanelSpecSummary } from "../../types/api";

/** A Panels tab section — the panel specialisation of the shared model. */
export type PanelSection = Section<PanelSpecSummary>;

/** Stable id for the project-local section (`{project}/previewers/`). */
export const PROJECT_SECTION_ID = "__this_project__";
/** Stable id for the user-wide library section (`~/.scistudio/previewers/`). */
export const USER_LIBRARY_SECTION_ID = "__user_library__";
/** Stable id for the core section (built-in fallbacks). */
export const CORE_SECTION_ID = "__core__";
/**
 * Fallback section for a package-tier panel whose distribution has no
 * name. The backend reports `owner_name` and an empty one must not make the
 * panel vanish; it collects here instead, in the same A→Z remainder every
 * real package name lands in.
 */
export const PACKAGES_SECTION_ID = "Packages";

/**
 * The section a panel belongs to — its discovery tier, then its package.
 * Same shape as `typeSectionIdFor` on the type side, with no `custom` origin:
 * the panel registry has no fourth drop-in kind (an unresolvable drop-in
 * never reaches the listing at all).
 */
export function panelSectionIdFor(panel: PanelSpecSummary): string {
  switch (panel.owner_kind) {
    case "project":
      return PROJECT_SECTION_ID;
    case "user":
      return USER_LIBRARY_SECTION_ID;
    case "core":
      return CORE_SECTION_ID;
    default:
      return panel.owner_name || PACKAGES_SECTION_ID;
  }
}

/**
 * FR-037-style teaching copy, the panel-side counterpart of the type
 * hints: for a user who has never heard of a panel drop-in, the empty
 * section is the only moment they are guaranteed to be looking at the place
 * it would live.
 */
export const MY_LIBRARY_EMPTY_HINT =
  "No previewers of your own yet. Save one here and every project can use it.";
export const THIS_PROJECT_EMPTY_HINT =
  "No previewers in this project yet. Previewers you add here stay with this project and win over every other tier.";

/**
 * The ordered head of the panel section list. This Project and My Library
 * lead — the two drop-in tiers are the sections the product asks users to
 * invest in, and both render even when empty (their `emptyHint`s). Core is a
 * declared slot so the built-in fallbacks keep a stable position, and package
 * panels close the list as the A→Z remainder — the same shape the Blocks
 * and Data types tabs use (`buildSections` always emits the remainder last),
 * so all three left-panel catalogues read identically.
 */
export const PANEL_SECTION_SLOTS: readonly SectionSlot[] = [
  { id: PROJECT_SECTION_ID, title: "This Project", emptyHint: THIS_PROJECT_EMPTY_HINT },
  { id: USER_LIBRARY_SECTION_ID, title: "My Library", emptyHint: MY_LIBRARY_EMPTY_HINT },
  { id: CORE_SECTION_ID, title: "Core" },
];

/** Human label for an owner tier, used on the card's tier row. */
export function ownerKindLabel(kind: PanelSpecSummary["owner_kind"]): string {
  switch (kind) {
    case "project":
      return "This Project";
    case "user":
      return "My Library";
    case "package":
      return "Package";
    default:
      return "Core";
  }
}

/** Text a panel is searched by: id, target type, owner, features. */
function panelHaystack(panel: PanelSpecSummary): string {
  return `${panel.panel_id} ${panel.target_type} ${panel.owner_name} ${panel.features.join(" ")}`;
}

/** Text-search filter. Panels have no facet chips (the tier sections
 *  already are the grouping a person scans by). */
export function filterPanels(
  panels: readonly PanelSpecSummary[],
  search: string,
): PanelSpecSummary[] {
  return filterItems(panels, search, panelHaystack);
}

/** True when a search term is narrowing the list. */
export function isFilteringPanels(search: string): boolean {
  return search.trim().length > 0;
}

const byId = (a: PanelSpecSummary, b: PanelSpecSummary): number =>
  a.panel_id.localeCompare(b.panel_id);

/**
 * Build the ordered Panels sections from the visible panels. Under an
 * active search the teaching empty states drop out (`withoutEmptyHints`) —
 * "No previewers of your own yet" is a statement about the library, not about
 * the current query.
 */
export function buildPanelSections(
  panels: readonly PanelSpecSummary[],
  search: string,
): PanelSection[] {
  const visible = filterPanels(panels, search);
  const slots = isFilteringPanels(search)
    ? withoutEmptyHints(PANEL_SECTION_SLOTS)
    : PANEL_SECTION_SLOTS;
  return buildSections(visible, panelSectionIdFor, slots, byId);
}

/**
 * The effective choice for `targetType`, or `null` when the type is unchosen.
 *
 * The listing is already the effective view — the backend collapses the
 * project layer over the user layer before serving it (#2049) — so this is a
 * plain lookup, not a merge.
 */
export function choiceForType(
  choices: readonly PanelChoice[],
  targetType: string,
): PanelChoice | null {
  return choices.find((choice) => choice.target_type === targetType) ?? null;
}

/**
 * Choices whose panel is not registered right now (`available: false`).
 * No card exists for a stale choice's panel, so without surfacing them
 * here a stale preference would be invisible — and un-clearable — from the
 * tab whose job is showing these choices.
 */
export function staleChoices(choices: readonly PanelChoice[]): PanelChoice[] {
  return choices.filter((choice) => !choice.available);
}
