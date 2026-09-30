/**
 * ADR-055 Spec 4 FR-007 — poll the `update` capability's status route.
 *
 * Update availability and active runs change while the backend runs, so the
 * status is read, not declared: once on mount, every 60 seconds, and whenever
 * the window regains focus (a user returning to the tab sees a fresh answer).
 * A failed read keeps the last answer — the backend may be mid-restart — and
 * the poll never navigates, reloads or restarts anything on its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { UpdateCapability } from "../../lib/capabilities";
import { fetchUpdateStatus, type UpdateStatus } from "./enterpriseApi";

/** The poll interval the shared capability contract fixes. */
export const UPDATE_POLL_INTERVAL_MS = 60_000;

export interface UseUpdateStatusResult {
  /** The latest valid answer, or `null` before the first one arrives. */
  status: UpdateStatus | null;
  /** Read the status now; resolves to the fresh answer, or `null` on failure. */
  refresh: () => Promise<UpdateStatus | null>;
}

export function useUpdateStatus(update: UpdateCapability | null): UseUpdateStatusResult {
  const statusUrl = update?.statusUrl ?? null;
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async (): Promise<UpdateStatus | null> => {
    if (statusUrl === null) return null;
    try {
      const next = await fetchUpdateStatus(statusUrl);
      if (next !== null && mounted.current) setStatus(next);
      return next;
    } catch {
      return null;
    }
  }, [statusUrl]);

  useEffect(() => {
    mounted.current = true;
    if (statusUrl === null) {
      return () => {
        mounted.current = false;
      };
    }
    void refresh();
    const timer = setInterval(() => void refresh(), UPDATE_POLL_INTERVAL_MS);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      mounted.current = false;
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [statusUrl, refresh]);

  return { status, refresh };
}
