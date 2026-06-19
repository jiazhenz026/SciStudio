// ADR-050 §2.5 — unified node status surface.
//
// A single fixed-geometry surface in the top-right corner of the square node
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

interface SurfaceStyle {
  /** Glyph rendered inside the corner badge. */
  glyph: string;
  /** Foreground (glyph) colour. */
  color: string;
  /** Background fill colour. */
  bg: string;
  /** Accessible label for the surface. */
  label: string;
  /** Spin the glyph (running). */
  spin?: boolean;
}

const RUNTIME_STYLES: Record<string, SurfaceStyle> = {
  idle: { glyph: "○", color: "#9CA3AF", bg: "rgba(156,163,175,0.18)", label: "Idle" },
  ready: { glyph: "◉", color: "#3B82F6", bg: "rgba(59,130,246,0.18)", label: "Ready" },
  running: {
    glyph: "⟳",
    color: "#3B82F6",
    bg: "rgba(59,130,246,0.18)",
    label: "Running",
    spin: true,
  },
  paused: { glyph: "⏸", color: "#F59E0B", bg: "rgba(245,158,11,0.18)", label: "Paused" },
  done: { glyph: "✓", color: "#22C55E", bg: "rgba(34,197,94,0.18)", label: "Done" },
  error: { glyph: "!", color: "#EF4444", bg: "rgba(239,68,68,0.18)", label: "Error" },
  cancelled: { glyph: "⊘", color: "#F97316", bg: "rgba(249,115,22,0.18)", label: "Cancelled" },
  skipped: { glyph: "⊘", color: "#9CA3AF", bg: "rgba(156,163,175,0.18)", label: "Skipped" },
};

const ERROR_STYLE: SurfaceStyle = {
  glyph: "!",
  color: "#EF4444",
  bg: "rgba(239,68,68,0.18)",
  label: "Error",
};

const WARNING_STYLE: SurfaceStyle = {
  glyph: "!",
  color: "#B45309",
  bg: "rgba(245,158,11,0.22)",
  label: "Warning",
};

export type ProblemSeverity = "none" | "warning" | "error";

export interface NodeStatusSurfaceProps {
  /** Runtime state — defaults to "idle" when unset. */
  status?: string;
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
  if (severity === "error" || status === "error") {
    return { style: ERROR_STYLE, kind: "error" };
  }
  if (severity === "warning") {
    return { style: WARNING_STYLE, kind: "warning" };
  }
  return { style: RUNTIME_STYLES[status] ?? RUNTIME_STYLES.idle, kind: "runtime" };
}

export function NodeStatusSurface({
  status,
  problemSeverity = "none",
  errorSummary,
  errorMessage,
  onErrorClick,
  onWarningClick,
}: NodeStatusSurfaceProps) {
  const runtime = status ?? "idle";
  const { style, kind } = resolveSurface(runtime, problemSeverity);

  // Tooltip carries the verbose detail that ADR-050 forbids in the body.
  const detail =
    kind === "error"
      ? (errorSummary ?? errorMessage ?? "Error — open Logs for details")
      : kind === "warning"
        ? "Warning — open Config for details"
        : style.label;

  const badge = (
    <span
      data-testid="node-status-surface"
      data-status={runtime}
      data-severity={problemSeverity}
      data-surface-kind={kind}
      role="img"
      aria-label={`${style.label} status`}
      title={detail}
      // Absolute corner placement: the surface is laid out relative to the
      // square body and overlaps its top-right corner. It contributes ZERO to
      // the node's measured geometry (FR-004/FR-011).
      className="pointer-events-none absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold leading-none shadow-sm"
      style={{ backgroundColor: style.bg, color: style.color }}
    >
      <span className={style.spin ? "inline-block animate-spin" : undefined}>{style.glyph}</span>
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
        className="nodrag absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1"
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
          role="img"
          aria-label={`${style.label} status`}
          className="flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold leading-none shadow-sm"
          style={{ backgroundColor: style.bg, color: style.color }}
        >
          <span className={style.spin ? "inline-block animate-spin" : undefined}>
            {style.glyph}
          </span>
        </span>
      </button>
    );
  }

  return badge;
}
