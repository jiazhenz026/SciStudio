/**
 * ADR-053 Learning Center (#2057) — where the step's target is on screen.
 *
 * FR-089's pointing needs one number set that two things read: the ring drawn
 * around the target and the placement of the step card. Both have to stay on
 * the target while the user pans the canvas, scrolls a panel, resizes the
 * window, or opens the tab the target lives in — so this tracks rather than
 * measures once.
 *
 * **Why a frame loop rather than observers.** The obvious construction is a
 * `ResizeObserver` on the element plus scroll and resize listeners. That misses
 * the case this feature exists for: a canvas node moves when React Flow pans or
 * zooms, which changes neither the element's box nor any scroll position this
 * could listen to — it is a transform on an ancestor. It also misses the target
 * appearing later, which is normal here, because a step routes to a tab and
 * then points at something inside it. A frame loop answers all of those with
 * one mechanism, and it runs only while a step is pointing at something.
 *
 * The loop is cheap by construction: one `querySelector` and one
 * `getBoundingClientRect` per frame, and React state is set only when the
 * measured box actually changes, so a still target re-renders nothing.
 */

import { useEffect, useRef, useState } from "react";

import type { TutorialHighlightView } from "../../lib/api/learningCenter";
import { panelHighlightRect, requestPanelHighlight } from "../../panels/panelHighlights";

import { findTutorialTarget, tutorialTargetKey } from "./targets";

/**
 * A target's box in viewport coordinates.
 *
 * Deliberately not a `DOMRect`: `getBoundingClientRect` returns a fresh object
 * every call, so comparing them requires reading the fields anyway, and holding
 * a live `DOMRect` in state invites reading it after it has gone stale.
 */
export interface HighlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function boxOf(element: Element): HighlightRect | null {
  if (typeof element.getBoundingClientRect !== "function") return null;
  const box = element.getBoundingClientRect();
  /*
   * A zero-sized box is a target that is in the DOM but not laid out — display
   * none, a collapsed panel, a tab that is mounted but not visible. Treating it
   * as "not found" is what makes the card fall back to the center instead of
   * cutting a hole of nothing out of the overlay.
   */
  if (box.width <= 0 || box.height <= 0) return null;
  return { top: box.top, left: box.left, width: box.width, height: box.height };
}

/**
 * The panel *element* has opened, if it has opened one.
 *
 * A target that opens a menu stops being the whole of what the step is about
 * the moment it is pressed: "press New, choose New custom block" points at the
 * button first and at the menu second, and the menu is several times the size
 * of the button that produced it. Measuring only the button let the card be
 * placed in space the menu was about to fill, so the card covered the entries
 * the step was telling the reader to choose from — FR-089's one rule, failed
 * against the half of the target that only exists once the reader acts.
 *
 * Read from ARIA rather than from any component's internals: an expanded
 * control points at what it expanded, which is a property of the accessibility
 * contract every menu, popover, and combobox in this product already honors,
 * and not of the library that happens to render them.
 */
function expandedPanelOf(element: Element): Element | null {
  if (element.getAttribute("aria-expanded") !== "true") return null;
  const controls = element.getAttribute("aria-controls");
  if (!controls) return null;
  return document.getElementById(controls);
}

/** The smallest box containing both, so placement clears the pair. */
function union(a: HighlightRect, b: HighlightRect): HighlightRect {
  const top = Math.min(a.top, b.top);
  const left = Math.min(a.left, b.left);
  return {
    top,
    left,
    width: Math.max(a.left + a.width, b.left + b.width) - left,
    height: Math.max(a.top + a.height, b.top + b.height) - top,
  };
}

function measure(highlight: TutorialHighlightView | null, owner: symbol): HighlightRect | null {
  if (!highlight) {
    requestPanelHighlight(owner, null);
    return null;
  }
  const element = findTutorialTarget(highlight.target, highlight.args);
  /*
   * A target inside a panel frame is in another document, so this walk cannot
   * find it and the step would degrade to a centred card with no ring — which
   * is what happened to every step pointing at a collection item once the
   * collection viewer became a panel. The frame measures its own element and
   * reports the box; `panelHighlightRect` adds the frame's current position.
   *
   * Asked for here, where the miss happens, rather than once per target: a
   * frame is asked only for what the host could not find, so the stage target —
   * which is always in the host document — never reaches a panel, and a target
   * that appears in the host later stops being asked for.
   */
  if (!element) {
    const key = tutorialTargetKey(highlight.target, highlight.args);
    requestPanelHighlight(owner, { target: highlight.target, key });
    return panelHighlightRect(highlight.target, key);
  }
  requestPanelHighlight(owner, null);
  const box = boxOf(element);
  if (!box) return null;
  const panel = expandedPanelOf(element);
  const panelBox = panel ? boxOf(panel) : null;
  return panelBox ? union(box, panelBox) : box;
}

function same(a: HighlightRect | null, b: HighlightRect | null): boolean {
  if (a === null || b === null) return a === b;
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

/**
 * Follow the element *highlight* names, or return `null` while there is none.
 *
 * `null` covers three cases the caller handles the same way: the step points at
 * nothing, the target is not on screen yet, and the target does not exist in
 * this build. All three mean "there is nothing to point at", and FR-089 puts
 * the card in the center of the screen with no overlay for all of them.
 */
export function useHighlightRect(highlight: TutorialHighlightView | null): HighlightRect | null {
  /*
   * This tracker's own identity. `ActiveStep` runs two of them — one for the
   * step's target and one for the stage the dialogue stands on — and a shared
   * slot let the second overwrite the first's request and either one's cleanup
   * clear the other's.
   */
  const owner = useRef<symbol>();
  if (owner.current === undefined) owner.current = Symbol("highlight-tracker");
  const self = owner.current;
  const [rect, setRect] = useState<HighlightRect | null>(() => measure(highlight, self));
  const current = useRef<HighlightRect | null>(rect);

  const target = highlight?.target ?? null;
  const args = JSON.stringify(highlight?.args ?? {});

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return;

    const view: TutorialHighlightView | null =
      target === null ? null : { target, args: JSON.parse(args) };
    let frame = 0;

    const tick = () => {
      const next = measure(view, self);
      if (!same(current.current, next)) {
        current.current = next;
        setRect(next);
      }
      frame = window.requestAnimationFrame(tick);
    };
    tick();

    return () => {
      window.cancelAnimationFrame(frame);
      requestPanelHighlight(self, null);
    };
  }, [target, args, self]);

  return rect;
}
