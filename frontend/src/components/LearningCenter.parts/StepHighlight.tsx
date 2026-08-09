/**
 * ADR-053 Learning Center (#2057) — the visible highlight for a step's target.
 *
 * A step's `highlight` used to be rendered as the words "Look for: canvas",
 * which told the user the name of a thing rather than showing them the thing.
 * This draws a ring around the annotated element instead.
 *
 * **It cannot occlude what it points at (FR-089).** The ring is a `fixed`
 * overlay drawn *around* the target's bounding box, with `pointer-events: none`
 * throughout, so every click, drag, and drop still lands on the element
 * underneath. That matters most for `canvas` and `block_palette`, where the
 * step is asking the user to drag one onto the other. The active-step strip is
 * separately in normal layout flow, so it does not overlap the target either.
 *
 * **Position is recomputed on an animation frame while a highlight is up.**
 * The alternative is subscribing to scroll, resize, panel drags, React Flow's
 * own pan and zoom, and the late mount of a tab that was just opened — five
 * listeners that each have to be right. One `getBoundingClientRect` per frame,
 * only while a tutorial is pointing at something, is the cheaper correctness.
 * It also means a target that has not rendered yet is picked up as soon as it
 * does, rather than being missed once and never retried.
 */

import { useEffect, useState } from "react";

import { useAppStore } from "../../store";
import { findTutorialTarget, isHighlightTarget } from "./targets";

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function sameBox(a: Box | null, b: Box | null): boolean {
  if (a === null || b === null) return a === b;
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

/** Padding between the target's edge and the ring, in pixels. */
const RING_INSET = 4;

export function StepHighlight() {
  const highlight = useAppStore((state) => state.learningCenterSession?.step?.highlight ?? null);
  const [box, setBox] = useState<Box | null>(null);

  useEffect(() => {
    if (!highlight || !isHighlightTarget(highlight)) {
      setBox(null);
      return;
    }

    let frame = 0;
    let current: Box | null = null;

    const track = () => {
      const element = findTutorialTarget(highlight);
      const next: Box | null = element
        ? (() => {
            const rect = element.getBoundingClientRect();
            // A zero-area rect means the element is mounted but not showing —
            // a panel dragged shut, say. Ringing nothing would be a floating
            // rectangle in the corner.
            if (rect.width === 0 || rect.height === 0) return null;
            return {
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
            };
          })()
        : null;

      if (!sameBox(current, next)) {
        current = next;
        setBox(next);
      }
      frame = window.requestAnimationFrame(track);
    };

    track();
    return () => window.cancelAnimationFrame(frame);
  }, [highlight]);

  if (!box) return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed z-40 rounded-xl border-2 border-ember shadow-[0_0_0_4px_rgba(240,106,68,0.18)] transition-[top,left,width,height] duration-150"
      data-testid="tutorial-step-highlight"
      style={{
        top: box.top - RING_INSET,
        left: box.left - RING_INSET,
        width: box.width + RING_INSET * 2,
        height: box.height + RING_INSET * 2,
      }}
    />
  );
}
