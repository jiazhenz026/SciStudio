// #1974 — elapsed-run timer shared by every "running" surface.
//
// Extracted from `BlockNode.parts/NodeStatusSurface.tsx` in #2190 so the plot
// card can show the same compact counter while a plot run is in flight. The
// formatting rules and the 1 Hz tick are a single contract: block nodes and
// plot cards must read identically.

import { useEffect, useState } from "react";

/** #1974 — the counter ticks once a second; sub-second precision is noise here. */
const ELAPSED_TICK_MS = 1000;

/**
 * #1974 — render the elapsed run time compactly: `7s` under a minute, `2:05`
 * under an hour, `1:04:09` beyond it. Seconds are floored so the counter reads
 * `0s` the instant the run starts rather than skipping ahead.
 */
export function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const paddedSeconds = String(seconds).padStart(2, "0");
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${paddedSeconds}`;
  if (minutes > 0) return `${minutes}:${paddedSeconds}`;
  return `${seconds}s`;
}

/**
 * #1974 — tick once a second while `startedAt` is set. Passing `null` (any
 * non-running state) tears the interval down, so a finished run holds no
 * timer, no duration, and no pending work.
 */
export function useElapsedMs(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, now - startedAt);
}
