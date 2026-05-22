/**
 * Date / duration formatters used by `RunDetail`.
 *
 * Extracted from `frontend/src/components/Lineage/RunDetail.tsx` (#1422).
 * Pure helpers — no React, no store, no Monaco. Trivially unit-testable.
 */

import type { LineageRunSummary } from "../../../types/lineage";

export function formatLocalDateTime(iso: string): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function formatDuration(run: LineageRunSummary): string {
  const ms = run.duration_ms;
  if (ms === null) {
    return run.status === "running" ? "in progress" : "—";
  }
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${s}s`;
}
