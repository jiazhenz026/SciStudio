// The activity bar's section order as a per-viewer UI preference (#2415).
//
// The order is how one person likes their rail arranged, so it lives in this
// browser's localStorage: it is not project state, it is not runtime state,
// and no backend ever reads it. The saved value is only a list of section
// keys; `mergeActivityBarOrder` reconciles it with the sections the build
// actually has, so an entry added or removed by a later release never leaves
// the rail with a gap or a stale icon.

import { useSyncExternalStore } from "react";

export const ACTIVITY_BAR_ORDER_STORAGE_KEY = "scistudio-activity-bar-order";
const CHANGE_EVENT = "scistudio:activity-bar-order-changed";

/**
 * Reconcile a saved order with the current default order.
 *
 * - Keys the build does not know, and repeated keys, are dropped.
 * - A default key missing from the saved order is inserted right after the
 *   nearest key that precedes it in the default order (or first, when none
 *   does), which is its default position relative to what the user kept.
 * - Anything that is not an array of strings yields the default order.
 */
export function mergeActivityBarOrder<K extends string>(
  saved: unknown,
  defaults: readonly K[],
): K[] {
  if (!Array.isArray(saved)) return [...defaults];
  const known = new Set<string>(defaults);
  const result: K[] = [];
  for (const key of saved) {
    if (typeof key === "string" && known.has(key) && !result.includes(key as K)) {
      result.push(key as K);
    }
  }
  defaults.forEach((key, index) => {
    if (result.includes(key)) return;
    let insertAt = 0;
    for (let prev = index - 1; prev >= 0; prev -= 1) {
      const at = result.indexOf(defaults[prev]);
      if (at !== -1) {
        insertAt = at + 1;
        break;
      }
    }
    result.splice(insertAt, 0, key);
  });
  return result;
}

/** Move `key` so it sits at `toIndex` in `order`; returns a new array. */
export function moveActivityBarKey<K extends string>(
  order: readonly K[],
  key: K,
  toIndex: number,
): K[] {
  const from = order.indexOf(key);
  if (from === -1) return [...order];
  const next = order.filter((entry) => entry !== key);
  const clamped = Math.max(0, Math.min(toIndex, next.length));
  next.splice(clamped, 0, key);
  return next;
}

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(ACTIVITY_BAR_ORDER_STORAGE_KEY);
  } catch {
    return null;
  }
}

function parse(raw: string | null): unknown {
  if (raw === null) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

/** Save an order. `null` clears the preference, restoring the default. */
export function saveActivityBarOrder(order: readonly string[] | null): void {
  try {
    if (order === null) {
      window.localStorage.removeItem(ACTIVITY_BAR_ORDER_STORAGE_KEY);
    } else {
      window.localStorage.setItem(ACTIVITY_BAR_ORDER_STORAGE_KEY, JSON.stringify(order));
    }
  } catch {
    // Storage unavailable (private mode, blocked site data): nothing is
    // saved, so the rail keeps the order it already shows.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === ACTIVITY_BAR_ORDER_STORAGE_KEY) onChange();
  };
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** The saved order merged against `defaults`; re-renders when it changes. */
export function useActivityBarOrder<K extends string>(defaults: readonly K[]): K[] {
  // The snapshot is the raw string so it is referentially stable between
  // renders; parsing happens after.
  const raw = useSyncExternalStore(subscribe, readRaw, () => null);
  return mergeActivityBarOrder(parse(raw), defaults);
}
