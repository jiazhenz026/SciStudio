import { useCallback, useEffect, useState } from "react";

/**
 * The tip overlay's visibility clock (#1997).
 *
 * The overlay covers the bottom of the left panel while it is up, so it earns
 * its place by leaving again. It alternates on a fixed cycle and gives the
 * user a way out that escalates: the first dismissal buys five quiet minutes,
 * the second silences the overlay for the rest of the session. A cycle that
 * ends on its own is the schedule doing its job rather than the user saying
 * anything, so it never counts toward that escalation.
 */

/** How long one tip stays up. Long enough to read a title and two lines. */
export const TIP_VISIBLE_MS = 40_000;
/** Quiet gap between tips, and the delay before the very first one. */
export const TIP_HIDDEN_MS = 40_000;
/** Quiet period bought by the first dismissal. */
export const TIP_SNOOZE_MS = 5 * 60_000;
/** Dismissals after which the overlay stays down for the session. */
export const TIP_DISMISSALS_BEFORE_SILENCE = 2;

export interface TipRotation {
  /** Whether the overlay should currently be showing. */
  readonly visible: boolean;
  /** Rotation position; grows without bound, resolved against the pool. */
  readonly index: number;
  /** True once the user has dismissed often enough to stop the rotation. */
  readonly silenced: boolean;
  /** User pressed the close control. */
  readonly dismiss: () => void;
}

interface Phase {
  readonly visible: boolean;
  /** How long this phase lasts before the rotation flips. */
  readonly delayMs: number;
  readonly index: number;
}

/**
 * `enabled` is false when there is nothing to show (an empty pool, or no
 * project open). The rotation then holds still rather than ticking against a
 * surface that will never render.
 */
export function useTipRotation(enabled: boolean): TipRotation {
  // A random start means two users opening the same project do not both see
  // the same tip first, which matters while the pool is small.
  const [phase, setPhase] = useState<Phase>(() => ({
    visible: false,
    delayMs: TIP_HIDDEN_MS,
    index: Math.floor(Math.random() * Number.MAX_SAFE_INTEGER),
  }));
  const [dismissals, setDismissals] = useState(0);
  const silenced = dismissals >= TIP_DISMISSALS_BEFORE_SILENCE;

  useEffect(() => {
    if (!enabled || silenced) {
      return;
    }
    const timer = setTimeout(() => {
      setPhase((prev) =>
        prev.visible
          ? { visible: false, delayMs: TIP_HIDDEN_MS, index: prev.index }
          : { visible: true, delayMs: TIP_VISIBLE_MS, index: prev.index + 1 },
      );
    }, phase.delayMs);
    return () => clearTimeout(timer);
  }, [enabled, silenced, phase]);

  const dismiss = useCallback(() => {
    setDismissals((count) => count + 1);
    // Advancing the index here means the tip the user just closed is not the
    // one waiting for them when the snooze runs out.
    setPhase((prev) => ({ visible: false, delayMs: TIP_SNOOZE_MS, index: prev.index + 1 }));
  }, []);

  return { visible: phase.visible && enabled, index: phase.index, silenced, dismiss };
}
