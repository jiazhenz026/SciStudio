/**
 * ADR-053 Learning Center (#2057) — FR-089a's outline on the step's target.
 *
 * The element the step points at gets a ring drawn around it, in the product's
 * accent colour, sitting a few pixels clear of the element's own box so it
 * reads as pointing rather than as a border the element grew.
 *
 * **Why not a dimming overlay.** Darkening everything else was tried first and
 * rejected by the owner on 2026-08-11 after using it: taking the whole window
 * down to say one thing is up makes the product feel like it has stopped
 * working, and the reader loses the surroundings they are being taught to
 * navigate. Pointing at one element is a small claim, and the small mechanism
 * is the honest one.
 *
 * This is not the ember ring removed on 2026-08-10 either, though it is closer.
 * That one was drawn permanently on the canvas at all times; this exists only
 * while a step is pointing at something, disappears the moment the step is
 * satisfied or the target leaves the screen, and never draws on a step that
 * points nowhere.
 *
 * **It never takes a click.** `pointer-events: none` on the container and the
 * ring, so every click lands on whatever is underneath as if this were not
 * here. A target that resolves to the wrong element must cost the reader a
 * moment of confusion, never the ability to use the product.
 */

import type { HighlightRect } from "./useHighlightRect";

/** How far the ring sits outside the target element, in pixels. */
const HALO = 5;

export function TargetHighlight({ rect }: { rect: HighlightRect | null }) {
  if (!rect) return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-40"
      data-testid="tutorial-highlight"
    >
      <div
        className="pointer-events-none absolute rounded-lg ring-[3px] ring-ember transition-all duration-200 ease-out"
        style={{
          top: rect.top - HALO,
          left: rect.left - HALO,
          width: rect.width + HALO * 2,
          height: rect.height + HALO * 2,
          /*
           * Two layers under the ring, because the ring alone has to survive
           * both a pale panel and the canvas's own grid. The near glow at 40%
           * is what makes it read as lit rather than as one more border in a UI
           * that already has many; the wide, faint one lifts it off whatever is
           * behind. An earlier single 18% glow was invisible in use.
           */
          boxShadow: "0 0 0 5px rgba(240, 106, 68, 0.40), 0 0 18px 6px rgba(240, 106, 68, 0.22)",
        }}
      />
    </div>
  );
}
