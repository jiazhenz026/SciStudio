/**
 * ADR-053 Learning Center (#2057) — the two step-guidance vocabularies.
 *
 * A step's `route_to` says where the user should be; its `highlight` says what
 * they should be looking at. Both are closed sets, validated against the
 * backend's own constants when a manifest loads, so an unknown value cannot
 * reach the frontend. This module is the single place the manifest's names are
 * translated into this UI's internals — put a new target here, not inline at a
 * call site, or the next reader will find two half-mappings that disagree.
 *
 * `highlight` renders as FR-089's pointing: the target is ringed where it sits
 * and the step's card is placed beside it. Two earlier forms were tried and
 * rejected by the owner — a permanent ember outline drawn on the canvas at all
 * times (2026-08-10), and dimming the rest of the window (2026-08-11, which
 * made the product read as having stopped working). What is left exists only
 * while a step is pointing at something and touches nothing else.
 *
 * **Why some manifest names differ from the internal keys.** Manifests are
 * written by tutorial authors and read by users, so they use the names the
 * product shows on screen. Two of them do not match the code:
 *
 *   - `history` → the `BottomTab` key `lineage`. The tab was renamed to
 *     "History" in the UI by owner request (#1713 follow-up) while the key and
 *     all the code behind it stayed `lineage`. `TabBar.tsx` now reads
 *     `lineage: tabLabel(History, "History")` (#2090 moved `Waypoints`
 *     to the activity bar's Workflows section).
 *   - `ai_chat` → the `BottomTab` key `ai`.
 *
 * The other five bottom-panel names match their keys exactly. Do not "fix"
 * either mapping by renaming a manifest name to match the code: the manifest
 * name is the user-facing one on purpose, and renaming it would break every
 * published tutorial that uses it.
 */

import type { LeftTab } from "../../App.parts/ProjectWorkspace";
import type { BottomTab } from "../../types/ui";

/**
 * The attribute that marks an element as a tutorial target.
 *
 * Separate from `data-testid` deliberately: a testid is a test's business and
 * may be renamed whenever a test is rewritten, while this one is part of a
 * contract with published tutorials.
 */
export const TUTORIAL_TARGET_ATTRIBUTE = "data-tutorial-target";

/** FR-089 companion — `route_to`'s closed set, mirroring `ROUTE_TARGETS`. */
export const ROUTE_TARGETS = [
  "ai_chat",
  "terminal",
  "config",
  "logs",
  "plots",
  "history",
  "git",
  "canvas",
  "block_palette",
  "data",
  "data_types",
  "workflows",
  "previewers",
] as const;

export type RouteTarget = (typeof ROUTE_TARGETS)[number];

/**
 * The main editing area, marked so the dialogue can be laid out inside it.
 *
 * Carried on the same attribute as a highlight target and deliberately absent
 * from `HIGHLIGHT_TARGETS`, so no manifest can name it: it is not something a
 * step points *at*, it is the box the character stands in. The canvas is inside
 * it, which is why the scene stays put when the canvas is what is showing, and
 * why she moves onto a code editor when that is what is showing instead.
 */
export const TUTORIAL_STAGE_TARGET = "workspace_stage";

/** `highlight`'s closed set, driven by what the core tutorials actually need. */
export const HIGHLIGHT_TARGETS = [
  "block_palette",
  "canvas",
  "run_button",
  "new_menu_button",
  "plots_new_button",
  "plot_export_button",
  "preview_item",
  "view_source_button",
  "history_restore_button",
  "history_runs_list",
  "bring_in_my_work_button",
  "data",
  "data_preview",
  "config_panel",
  "workflow_list",
  "ai_provider_picker",
  "ai_permission_modes",
  "previewer_palette",
  "type_palette",
  "palette_block",
  "node",
  "plot_card",
  "bottom_tab",
] as const;

export type HighlightTarget = (typeof HIGHLIGHT_TARGETS)[number];

/**
 * The argument each entity target is addressed by, mirroring the backend's
 * `HIGHLIGHT_SPECS[].required`.
 *
 * A target listed here annotates many elements, and the value of this argument
 * is what tells them apart: the palette renders one entry per block and every
 * one of them carries `data-tutorial-target="palette_block"`, so the lookup
 * needs `data-tutorial-target-key="load_data"` to pick one. A target absent
 * from this map annotates a single element and its name is the whole address.
 *
 * Exhaustive against the backend by a parity test rather than by construction,
 * because the two sides are in different languages; a target that grew a
 * required argument the frontend does not read would resolve to nothing and the
 * step would point at empty space.
 */
export const HIGHLIGHT_TARGET_KEYS: Partial<Record<HighlightTarget, string>> = {
  palette_block: "block_type",
  node: "block_type",
  plot_card: "plot_id",
  preview_item: "index",
  // Spelled the manifest's way, not `BottomTab`'s -- see the module comment on
  // `history`/`lineage` and `ai_chat`/`ai`. `BOTTOM_TAB_TUTORIAL_NAMES` below is
  // what the tab strip annotates itself with, so the two never drift.
  bottom_tab: "tab",
};

/** The attribute carrying an entity target's selector value. */
export const TUTORIAL_TARGET_KEY_ATTRIBUTE = "data-tutorial-target-key";

/**
 * Manifest route name → bottom-panel tab key, or `null` for the two targets
 * that are not tabs at all.
 *
 * Exhaustive over `RouteTarget` by type, so adding a route target without
 * deciding what it means here fails the typecheck rather than silently doing
 * nothing at runtime.
 */
export const ROUTE_TARGET_BOTTOM_TABS: Record<RouteTarget, BottomTab | null> = {
  ai_chat: "ai", // renamed — see the module comment
  terminal: "terminal",
  config: "config",
  logs: "logs",
  plots: "plots",
  history: "lineage", // renamed — see the module comment
  git: "git",
  canvas: null,
  block_palette: null,
  data: null,
  data_types: null,
  workflows: null,
  previewers: null,
};

/**
 * Manifest route name → left-panel tab, for the targets that live there.
 *
 * `block_palette` is the palette the user drags blocks from, which sits on the
 * left panel's "blocks" tab. A step telling someone to drag a Load block while
 * they are looking at the Project tree is the dead end this avoids.
 */
export const ROUTE_TARGET_LEFT_TABS: Partial<Record<RouteTarget, LeftTab>> = {
  block_palette: "blocks",
  // The Data section (#2090): the project's data/ tree, which is where a
  // reader looks to find out what an experiment actually shipped with. Core
  // tutorial 3 opens there, because the whole level turns on what is in the
  // file — and on what is only in its name.
  data: "data",
  // The Data types tab between Blocks and Project — the manifest name is the
  // user-facing label ("Data types"), the internal key stays `types`, on the
  // same rule as `history`/`lineage` above.
  data_types: "types",
  // The Workflows section of the left panel (#2090). Core tutorial 1 opens by
  // showing the reader where this project's workflows are kept, which only
  // works if the panel is showing them.
  workflows: "workflows",
  // The Previewers section (#2113): the cards that say which previewer renders
  // which kind of data. A step pointing at them has to have the panel showing
  // them first.
  previewers: "previewers",
};

/**
 * Bottom-panel tab key -> the name a manifest addresses it by.
 *
 * The inverse of the routing map above rather than a second table: a step that
 * says `route_to: history` and rings `bottom_tab: {tab: history}` is naming one
 * destination once, and two hand-written maps would eventually disagree about
 * which word that is. Every `BottomTab` appears in the routing map, so the
 * inversion is total; a parity test holds that true.
 */
export const BOTTOM_TAB_TUTORIAL_NAMES = Object.fromEntries(
  (Object.entries(ROUTE_TARGET_BOTTOM_TABS) as [RouteTarget, BottomTab | null][])
    .filter((entry): entry is [RouteTarget, BottomTab] => entry[1] !== null)
    .map(([route, tab]) => [tab, route]),
) as Record<BottomTab, RouteTarget>;

export function isRouteTarget(value: string): value is RouteTarget {
  return (ROUTE_TARGETS as readonly string[]).includes(value);
}

export function isHighlightTarget(value: string): value is HighlightTarget {
  return (HIGHLIGHT_TARGETS as readonly string[]).includes(value);
}

/** The selector that finds an annotated element. */
export function tutorialTargetSelector(target: string, args: Record<string, string> = {}): string {
  const base = `[${TUTORIAL_TARGET_ATTRIBUTE}="${CSS.escape(target)}"]`;
  const keyName = HIGHLIGHT_TARGET_KEYS[target as HighlightTarget];
  const key = keyName === undefined ? undefined : args[keyName];
  if (key === undefined) return base;
  return `${base}[${TUTORIAL_TARGET_KEY_ATTRIBUTE}="${CSS.escape(key)}"]`;
}

export function findTutorialTarget(
  target: string,
  args: Record<string, string> = {},
): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(tutorialTargetSelector(target, args));
}

export interface StepRouteHandlers {
  /**
   * The store's `openBottomTab`, never `setActiveBottomTab`.
   *
   * Selecting a tab is not enough when the panel is collapsed: the tab would
   * change behind a closed panel and, from the user's side, a step that said
   * "go to History" would have done nothing. `openBottomTab` expands and
   * selects in one action.
   */
  openBottomTab: (tab: BottomTab) => void;
  setLeftTab: (tab: LeftTab) => void;
  /**
   * Bring the workflow canvas back to the front of the main area.
   *
   * The main area is a tab strip, and a code editor opened over it hides the
   * canvas completely. A step saying "drag it onto the canvas" while a `.py`
   * file is on screen is an instruction the reader cannot follow and cannot see
   * is impossible — and the tutorial has just been the thing that opened that
   * editor. A no-op when no workflow tab is open, which is the case a reading
   * tutorial with no project is in.
   */
  showCanvas: () => void;
}

/**
 * Take the user where the step says to be.
 *
 * `canvas` and `block_palette` are not bottom-panel tabs, so "routing" to them
 * means something different, and this is the choice made for each:
 *
 *   - `block_palette` switches the left panel to its Blocks tab. That is a real
 *     surface switch with the same shape as a bottom-tab one.
 *   - `canvas` brings the workflow tab to the front of the main area, and does
 *     nothing else. It used to switch nothing at all, on the reasoning that the
 *     canvas is the main surface and is already on screen — true until the
 *     tutorial itself opens a code editor over it, which core tutorial 1 does
 *     when the reader creates a block. The next step then said "drag it onto
 *     the canvas" with a `.py` file filling the screen. Restoring the tab is
 *     not fighting a layout the user chose: it is undoing one the tutorial
 *     chose. Everything else about the layout — the bottom panel's height, its
 *     open tab — is still left exactly as found.
 *
 * Both then scroll their element into view, which is also all a target does
 * when its surface is already the visible one.
 */
/**
 * Replay surface → the bottom-panel tab that shows it.
 *
 * A separate question from `route_to`: that says where the *step* wants the
 * reader, this says where the *reply* is being typed. They are usually the
 * same tab and occasionally not — a step ringing a palette entry routes the
 * left panel and still has a reply arriving in AI Chat — and only one of them
 * can be a property of the step.
 */
export const REPLAY_SURFACE_BOTTOM_TABS: Record<string, BottomTab> = {
  ai_chat_terminal: "ai",
};

/** The tab a reply on *surface* lands in, or null for a surface with no tab. */
export function bottomTabForReplaySurface(surface: string): BottomTab | null {
  return REPLAY_SURFACE_BOTTOM_TABS[surface] ?? null;
}

export function applyStepRoute(route: string, handlers: StepRouteHandlers): void {
  if (!isRouteTarget(route)) return;

  const bottomTab = ROUTE_TARGET_BOTTOM_TABS[route];
  if (bottomTab) handlers.openBottomTab(bottomTab);

  const leftTab = ROUTE_TARGET_LEFT_TABS[route];
  if (leftTab) handlers.setLeftTab(leftTab);

  /*
   * `block_palette` brings the canvas with it. The palette exists to be dragged
   * *from*, onto the canvas — a step routed there while a code editor covers
   * the canvas is asking for a drag with nowhere to drop, and core tutorial 1
   * opens exactly that editor one step earlier.
   */
  if (route === "canvas" || route === "block_palette") handlers.showCanvas();

  /*
   * After the surface switch, not before: the element a tab was just opened to
   * show does not exist until that render lands.
   */
  scrollTutorialTargetIntoView(route);
}

/**
 * Best-effort — a target that is not on screen is not an error.
 *
 * The `scrollIntoView` capability check is not ceremony. This runs inside a
 * `requestAnimationFrame` callback, which is outside every caller's try/catch
 * and outside React's error boundaries, so a host that does not implement the
 * method turns a nicety that failed into an uncaught exception. Declining to
 * scroll is what "best-effort" is supposed to mean.
 */
export function scrollTutorialTargetIntoView(
  target: string,
  args: Record<string, string> = {},
): void {
  if (typeof window === "undefined") return;
  window.requestAnimationFrame(() => {
    const element = findTutorialTarget(target, args);
    if (typeof element?.scrollIntoView === "function") {
      element.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  });
}
