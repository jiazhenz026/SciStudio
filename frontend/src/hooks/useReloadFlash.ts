import { useEffect, useRef } from "react";

/**
 * One-shot "browser-refresh" opacity blink for a panel after a user-initiated
 * reload actually lands.
 *
 * Call `trigger()` on the reload/refresh click, attach `ref` to the element to
 * blink, and pass the freshly loaded data as `watched`. The blink fires only
 * when `watched` next changes after a `trigger()` — so it confirms the refresh
 * really happened, and never fires on mount, on background syncs, or on a
 * failed reload.
 *
 * The Web Animations API replays cleanly without remounting the subtree (which
 * would drop transient UI state like expand/collapse). It is guarded for jsdom,
 * which does not implement `Element.animate`.
 */
export function useReloadFlash<E extends HTMLElement, T>(watched: T) {
  const ref = useRef<E | null>(null);
  const requested = useRef(false);

  useEffect(() => {
    if (!requested.current) {
      return;
    }
    requested.current = false;
    ref.current?.animate?.([{ opacity: 1 }, { opacity: 0 }, { opacity: 1 }], {
      duration: 100,
      easing: "ease-out",
    });
  }, [watched]);

  const trigger = () => {
    requested.current = true;
  };

  return { ref, trigger };
}
