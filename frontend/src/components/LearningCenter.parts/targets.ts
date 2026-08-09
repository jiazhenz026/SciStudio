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
 * **Why some manifest names differ from the internal keys.** Manifests are
 * written by tutorial authors and read by users, so they use the names the
 * product shows on screen. Two of them do not match the code:
 *
 *   - `history` → the `BottomTab` key `lineage`. The tab was renamed to
 *     "History" in the UI by owner request (#1713 follow-up) while the key and
 *     all the code behind it stayed `lineage`. `TabBar.tsx` still reads
 *     `lineage: tabLabel(Waypoints, "History")`.
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
] as const;

export type RouteTarget = (typeof ROUTE_TARGETS)[number];

/** `highlight`'s closed set, driven by what the core tutorials actually need. */
export const HIGHLIGHT_TARGETS = [
  "block_palette",
  "canvas",
  "run_button",
  "plots_new_button",
  "history_restore_button",
  "data_preview",
] as const;

export type HighlightTarget = (typeof HIGHLIGHT_TARGETS)[number];

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
};

export function isRouteTarget(value: string): value is RouteTarget {
  return (ROUTE_TARGETS as readonly string[]).includes(value);
}

export function isHighlightTarget(value: string): value is HighlightTarget {
  return (HIGHLIGHT_TARGETS as readonly string[]).includes(value);
}

/** The selector that finds an annotated element. */
export function tutorialTargetSelector(target: string): string {
  return `[${TUTORIAL_TARGET_ATTRIBUTE}="${target}"]`;
}

export function findTutorialTarget(target: string): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(tutorialTargetSelector(target));
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
}

/**
 * Take the user where the step says to be.
 *
 * `canvas` and `block_palette` are not bottom-panel tabs, so "routing" to them
 * means something different, and this is the choice made for each:
 *
 *   - `block_palette` switches the left panel to its Blocks tab. That is a real
 *     surface switch with the same shape as a bottom-tab one.
 *   - `canvas` switches nothing. The canvas is the main surface and is already
 *     on screen whenever a workflow tab is active; there is no panel to open
 *     and forcing anything else — collapsing the bottom panel, say — would be
 *     the product fighting a layout the user chose. It scrolls into view and
 *     leaves the highlight to say the rest.
 *
 * Both then scroll their element into view, which is also all a target does
 * when its surface is already the visible one.
 */
export function applyStepRoute(route: string, handlers: StepRouteHandlers): void {
  if (!isRouteTarget(route)) return;

  const bottomTab = ROUTE_TARGET_BOTTOM_TABS[route];
  if (bottomTab) handlers.openBottomTab(bottomTab);

  const leftTab = ROUTE_TARGET_LEFT_TABS[route];
  if (leftTab) handlers.setLeftTab(leftTab);

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
export function scrollTutorialTargetIntoView(target: string): void {
  if (typeof window === "undefined") return;
  window.requestAnimationFrame(() => {
    const element = findTutorialTarget(target);
    if (typeof element?.scrollIntoView === "function") {
      element.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  });
}
