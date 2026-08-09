import { Lightbulb, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PALETTE_TIPS, resolveTip } from "./tipPool";
import { useTipRotation } from "./useTipRotation";

/**
 * The tip overlay (#1997): a small card that fades in over the bottom of the
 * left panel, carrying one tip at a time.
 *
 * It sits on the panel rather than inside any one tab, so the same card and
 * the same clock serve Blocks, Data types, and Project. Switching tabs neither
 * restarts the rotation nor makes the card flicker, and every tip is shown on
 * every tab (owner directive, #1997).
 *
 * It overlays instead of taking a row of its own so the block grid keeps its
 * full height, and it is hidden with opacity rather than unmounted so the fade
 * has something to animate. `pointer-events-none` while hidden is what keeps
 * the covered tiles clickable during the quiet half of the cycle.
 */

export function PaletteTipCard() {
  const rotation = useTipRotation(PALETTE_TIPS.length > 0);
  const tip = resolveTip(rotation.index);

  const [expanded, setExpanded] = useState(false);
  // The card holds a constant height as the panel is resized: title and body
  // each stay clamped to two lines and text that no longer fits becomes
  // expandable rather than making the card grow (owner directive, #1997).
  const [clamped, setClamped] = useState(false);
  const bodyRef = useRef<HTMLParagraphElement | null>(null);
  const titleRef = useRef<HTMLSpanElement | null>(null);

  const tipId = tip?.id;
  // A new tip arrives collapsed; carrying the previous expansion over would
  // let one long tip silently resize the card for every tip after it.
  useEffect(() => setExpanded(false), [tipId]);

  useEffect(() => {
    const nodes = [titleRef.current, bodyRef.current].filter(
      (node): node is HTMLElement => node !== null,
    );
    if (nodes.length === 0 || expanded || typeof ResizeObserver === "undefined") {
      return;
    }
    // Either half can be the one that overflows — a long title at panel width,
    // a long body at any width — and one expand control releases both.
    const measure = () =>
      setClamped(nodes.some((node) => node.scrollHeight > node.clientHeight + 1));
    const observer = new ResizeObserver(measure);
    nodes.forEach((node) => observer.observe(node));
    measure();
    return () => observer.disconnect();
  }, [tipId, expanded]);

  if (rotation.silenced || !tip) {
    return null;
  }

  return (
    <div
      // The fill is ember at ~10% over white, flattened to an opaque hex on
      // purpose: the card sits on top of the tile grid, and a translucent
      // background would let block swatches show through the body text.
      className={`absolute inset-x-2 bottom-2 z-10 rounded-xl border-2 border-ember bg-[#fff1ec] p-[18px] shadow-panel transition-opacity duration-500 ${
        rotation.visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
      data-testid="palette-tip"
      // The overlay is advisory and arrives unprompted, so it announces itself
      // politely instead of interrupting whatever the user is doing.
      aria-live="polite"
      aria-hidden={rotation.visible ? undefined : true}
    >
      <div className="flex items-start justify-between gap-2">
        {/* `min-w-0` keeps the title from pushing the close control off the
            card. It wraps to a second line rather than truncating (owner
            directive, #1997): a title cut mid-word at panel width tells the
            user less than a two-line title does, and the card is anchored to
            the panel's bottom edge, so the extra line grows upward over the
            tile grid instead of displacing anything. */}
        <p className="flex min-w-0 items-start gap-1.5 font-display text-[15px] font-semibold text-ember">
          <Lightbulb className="mt-[3px] shrink-0" size={16} strokeWidth={2.25} />
          <span className={expanded ? "" : "line-clamp-2"} ref={titleRef}>
            {tip.title}
          </span>
        </p>
        <button
          aria-label="Dismiss tip"
          className="-mr-1 -mt-1 shrink-0 rounded p-0.5 text-stone-400 transition hover:text-ink"
          onClick={rotation.dismiss}
          type="button"
        >
          <X size={16} strokeWidth={2.25} />
        </button>
      </div>

      <p
        className={`mt-2 text-sm leading-relaxed text-stone-700 ${expanded ? "" : "line-clamp-2"}`}
        ref={bodyRef}
      >
        {tip.body}
      </p>

      {clamped || expanded ? (
        <button
          className="mt-1 text-[13px] font-medium text-ember transition hover:underline"
          onClick={() => setExpanded((prev) => !prev)}
          type="button"
        >
          {expanded ? "Less" : "More"}
        </button>
      ) : null}
    </div>
  );
}
