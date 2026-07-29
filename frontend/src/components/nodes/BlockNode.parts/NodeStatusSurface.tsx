// ADR-050 §2.5 — unified node status surface.
//
// A single fixed-geometry surface in the bottom-right corner of the square node
// that represents BOTH the runtime state (idle/ready/running/paused/done/
// error/cancelled/skipped) AND the problem severity (none/warning/error).
//
// Rules (ADR-050 §2.5, FR-004/FR-011):
//   - It is a corner glyph (dot / ring / badge), never a text row, footer,
//     inline message, or warning chip inside the body.
//   - It MUST NOT change the node's width or height in any state.
//   - Priority: error (problem OR runtime) > warning > runtime state. Error
//     has the highest priority and, on activation, selects the node + opens
//     Logs via `onErrorClick` (FR-012). Warning, on activation, selects the
//     node + opens BottomPanel Config via `onWarningClick` (FR-013).
//   - Verbose error text / lossy-save detail / warning lists live in Logs,
//     BottomPanel, or the tooltip `title`, never in the node body.
//
// #1974 — while (and only while) the runtime state is `running`, a compact
// elapsed-time counter sits immediately left of the spinner so a long-running
// block reads as "still working, for this long". It is an absolutely-positioned
// overlay like the badge itself: it contributes ZERO measured geometry, it is
// not a status footer/text row inside the body (FR-004), and it is transient —
// it unmounts on the first non-running state, leaving NO final duration and NO
// history of previous runs on the node.

import {
  AlertTriangle,
  Ban,
  Check,
  Circle,
  CircleDot,
  LoaderCircle,
  Minus,
  Pause,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

interface SurfaceStyle {
  /** Icon rendered inside the corner badge. */
  Icon: LucideIcon;
  /** Stable icon identifier for tests and visual debugging. */
  iconName: string;
  /** Foreground (glyph) colour. */
  color: string;
  /** Accessible label for the surface. */
  label: string;
  /** Spin the glyph (running). */
  spin?: boolean;
}

const STATUS_BADGE_BACKGROUND = "rgba(255, 255, 255, 0.86)";
const STATUS_BADGE_BORDER = "rgba(15, 23, 42, 0.14)";
const ERROR_STATUSES = new Set(["error", "fail", "failed", "failure"]);
/** #1974 — the counter ticks once a second; sub-second precision is noise here. */
const ELAPSED_TICK_MS = 1000;

const RUNTIME_STYLES: Record<string, SurfaceStyle> = {
  idle: { Icon: Circle, iconName: "circle", color: "#8A94A6", label: "Idle" },
  ready: { Icon: CircleDot, iconName: "circle-dot", color: "#2563EB", label: "Ready" },
  running: {
    Icon: LoaderCircle,
    iconName: "loader-circle",
    color: "#2563EB",
    label: "Running",
    spin: true,
  },
  paused: { Icon: Pause, iconName: "pause", color: "#D97706", label: "Paused" },
  done: { Icon: Check, iconName: "check", color: "#16A34A", label: "Done" },
  success: { Icon: Check, iconName: "check", color: "#16A34A", label: "Done" },
  succeeded: { Icon: Check, iconName: "check", color: "#16A34A", label: "Done" },
  completed: { Icon: Check, iconName: "check", color: "#16A34A", label: "Done" },
  error: { Icon: X, iconName: "x", color: "#DC2626", label: "Error" },
  fail: { Icon: X, iconName: "x", color: "#DC2626", label: "Error" },
  failed: { Icon: X, iconName: "x", color: "#DC2626", label: "Error" },
  failure: { Icon: X, iconName: "x", color: "#DC2626", label: "Error" },
  cancelled: { Icon: Ban, iconName: "ban", color: "#EA580C", label: "Cancelled" },
  skipped: { Icon: Minus, iconName: "minus", color: "#6B7280", label: "Skipped" },
};

const ERROR_STYLE: SurfaceStyle = {
  Icon: X,
  iconName: "x",
  color: "#DC2626",
  label: "Error",
};

const WARNING_STYLE: SurfaceStyle = {
  Icon: AlertTriangle,
  iconName: "alert-triangle",
  color: "#B45309",
  label: "Warning",
};

export type ProblemSeverity = "none" | "warning" | "error";

/**
 * #1974 — render the elapsed run time compactly: `7s` under a minute, `2:05`
 * under an hour, `1:04:09` beyond it. Seconds are floored so the counter reads
 * `0s` the instant the block starts rather than skipping ahead.
 */
function formatElapsed(elapsedMs: number): string {
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
 * non-running state) tears the interval down, so a finished node holds no
 * timer, no duration, and no pending work.
 */
function useElapsedMs(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, now - startedAt);
}

export interface NodeStatusSurfaceProps {
  /** Runtime state — defaults to "idle" when unset. */
  status?: string;
  /**
   * #1974 — epoch-ms instant this block entered the running state (engine
   * clock, carried by the `block_running` event). Set ONLY while running; the
   * counter renders alongside the spinner and disappears with it.
   */
  runStartedAt?: number;
  /** Highest-priority problem signal (ADR-050 §2.5). */
  problemSeverity?: ProblemSeverity;
  /** Concise error detail surfaced in the tooltip (never inline). */
  errorSummary?: string;
  errorMessage?: string;
  /** FR-012 — error activation: select node + open Logs. */
  onErrorClick?: () => void;
  /** FR-013 — warning activation: select node + open BottomPanel Config. */
  onWarningClick?: () => void;
}

/**
 * Resolve the single surface style to render, applying the ADR-050 §2.5
 * priority table: an `error` runtime state OR an `error` problem severity wins;
 * a `warning` problem severity overlays non-error runtime states; otherwise the
 * runtime state's own style is used.
 */
function resolveSurface(
  status: string,
  severity: ProblemSeverity,
): { style: SurfaceStyle; kind: "error" | "warning" | "runtime" } {
  if (severity === "error" || ERROR_STATUSES.has(status)) {
    return { style: ERROR_STYLE, kind: "error" };
  }
  if (severity === "warning") {
    return { style: WARNING_STYLE, kind: "warning" };
  }
  return { style: RUNTIME_STYLES[status] ?? RUNTIME_STYLES.idle, kind: "runtime" };
}

export function NodeStatusSurface({
  status,
  runStartedAt,
  problemSeverity = "none",
  errorSummary,
  errorMessage,
  onErrorClick,
  onWarningClick,
}: NodeStatusSurfaceProps) {
  const runtime = status ?? "idle";
  const { style, kind } = resolveSurface(runtime, problemSeverity);
  const Icon = style.Icon;

  // #1974 — the counter is bound to the SPINNER, not to the raw status: an
  // error/warning surface replaces the running glyph (§2.5 priority table), so
  // it must not keep a timer next to a glyph that no longer spins.
  const elapsedAnchor =
    kind === "runtime" && style.spin === true && typeof runStartedAt === "number"
      ? runStartedAt
      : null;
  const elapsedMs = useElapsedMs(elapsedAnchor);

  // Tooltip carries the verbose detail that ADR-050 forbids in the body.
  const detail =
    kind === "error"
      ? (errorSummary ?? errorMessage ?? "Error — open Logs for details")
      : kind === "warning"
        ? "Warning — open Config for details"
        : style.label;

  // Elapsed pill — absolute, pointer-events-none, sits just left of the badge.
  // Same zero-geometry contract as the badge (FR-004/FR-011).
  const elapsed =
    elapsedAnchor === null ? null : (
      <span
        data-testid="node-status-elapsed"
        aria-label={`Running for ${formatElapsed(elapsedMs)}`}
        title={`Running for ${formatElapsed(elapsedMs)}`}
        className="pointer-events-none absolute right-7 bottom-1 flex h-5 items-center rounded-full border px-1.5 font-mono text-[10px] font-semibold tabular-nums shadow-sm backdrop-blur-[1px]"
        style={{
          backgroundColor: STATUS_BADGE_BACKGROUND,
          borderColor: STATUS_BADGE_BORDER,
          color: style.color,
        }}
      >
        {formatElapsed(elapsedMs)}
      </span>
    );

  const badge = (
    <span
      data-testid="node-status-surface"
      data-status={runtime}
      data-severity={problemSeverity}
      data-surface-kind={kind}
      data-icon={style.iconName}
      role="img"
      aria-label={`${style.label} status`}
      title={detail}
      // Absolute corner placement: the surface is laid out relative to the
      // square body and overlaps its bottom-right corner. It contributes ZERO to
      // the node's measured geometry (FR-004/FR-011).
      className="pointer-events-none absolute right-1 bottom-1 flex h-5 w-5 items-center justify-center rounded-full border shadow-sm backdrop-blur-[1px]"
      style={{
        backgroundColor: STATUS_BADGE_BACKGROUND,
        borderColor: STATUS_BADGE_BORDER,
        color: style.color,
      }}
    >
      <Icon
        aria-hidden="true"
        className={style.spin ? "animate-spin" : undefined}
        size={13}
        strokeWidth={3}
      />
    </span>
  );

  // Activation affordance: error opens Logs, warning opens Config. Both select
  // the node first (the App-level handler does the selection). The button is a
  // zero-geometry overlay around the badge so clicking the corner works.
  const activate =
    kind === "error" ? onErrorClick : kind === "warning" ? onWarningClick : undefined;

  if (activate) {
    return (
      <button
        type="button"
        data-testid="node-status-surface-button"
        aria-label={kind === "error" ? "Open error logs" : "Open warning detail"}
        title={detail}
        className="nodrag absolute right-1 bottom-1 h-5 w-5 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1"
        onClick={(event) => {
          event.stopPropagation();
          activate();
        }}
      >
        <span
          data-testid="node-status-surface"
          data-status={runtime}
          data-severity={problemSeverity}
          data-surface-kind={kind}
          data-icon={style.iconName}
          role="img"
          aria-label={`${style.label} status`}
          className="flex h-5 w-5 items-center justify-center rounded-full border shadow-sm backdrop-blur-[1px]"
          style={{
            backgroundColor: STATUS_BADGE_BACKGROUND,
            borderColor: STATUS_BADGE_BORDER,
            color: style.color,
          }}
        >
          <Icon
            aria-hidden="true"
            className={style.spin ? "animate-spin" : undefined}
            size={13}
            strokeWidth={3}
          />
        </span>
      </button>
    );
  }

  return (
    <>
      {elapsed}
      {badge}
    </>
  );
}
