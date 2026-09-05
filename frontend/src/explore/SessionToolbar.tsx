/**
 * ADR-054 spec 4 (T-002) — the session toolbar's frame.
 *
 * The frame and the notebook toggle are here; every other control the toolbar
 * carries belongs to whoever owns that part of FR-014, and each of them is one
 * region component in `regions/ExploreRegions.tsx`:
 *
 *   - run-stale, interrupt, restart, commit — `ToolbarRunControls` (S4-A2)
 *   - the kernel list and package           — `ToolbarKernelControls` (S4-A4)
 *   - confirm and cancel, in pause mode     — `ToolbarPauseControls` (S4-A3)
 *
 * The toolbar renders in the centre column, above the strip, so FR-006 holds
 * without any special case: collapsing the right pane takes the notebook away
 * and leaves the toolbar and the panels exactly where they were.
 */

import type { ExploreSessionState, ExploreTab } from "../store/types";

import {
  ToolbarKernelControls,
  ToolbarPauseControls,
  ToolbarRunControls,
} from "./regions/ExploreRegions";

export interface SessionToolbarProps {
  tab: ExploreTab;
  /** `undefined` until the open or restore lands. */
  session: ExploreSessionState | undefined;
  /**
   * FR-014 / FR-026 — the notebook toggle.
   *
   * In a session tab it collapses and restores the notebook pane; in a pause
   * tab it is the control that opens a notebook over the paused run's inputs,
   * which is why the label reads differently in the two modes.
   */
  onToggleNotebook: () => void;
  /** FR-032 — whether the centre is showing the graph instead of the panels. */
  graphVisible: boolean;
  onToggleGraph: () => void;
}

/**
 * The kernel state the toolbar shows (FR-016).
 *
 * The one place the flag and the state are collapsed into a single word, and
 * it is a *rendering*, not a stored value: the slice keeps the runtime's state
 * and its `needsRestart` flag apart, because it is the runtime that said both.
 */
export function kernelLabel(session: ExploreSessionState | undefined): string {
  if (!session) return "opening";
  if (session.kernel.needsRestart) return "needs restart";
  return session.kernel.state;
}

export function SessionToolbar({
  tab,
  session,
  onToggleNotebook,
  graphVisible,
  onToggleGraph,
}: SessionToolbarProps) {
  const regionProps = { tab, session };
  return (
    <div
      className="flex flex-wrap items-center gap-3 border-b border-stone-200 bg-white/70 px-3 py-2"
      data-testid="explore-session-toolbar"
    >
      <span className="font-display text-sm text-ink" data-testid="explore-toolbar-title">
        {tab.displayName}
      </span>
      <span
        className="rounded-full border border-stone-300 px-2 py-0.5 text-[11px] text-stone-500"
        data-testid="explore-toolbar-kernel-state"
      >
        {kernelLabel(session)}
      </span>

      {/* FR-013, FR-014 — S4-A2's controls. */}
      <ToolbarRunControls {...regionProps} />

      {/* FR-014 to FR-016, FR-028 — S4-A4's controls. */}
      <ToolbarKernelControls {...regionProps} />

      {/* FR-024, FR-025 — S4-A3's controls, and only in pause mode. */}
      {tab.mode === "pause" ? <ToolbarPauseControls {...regionProps} /> : null}

      <div className="ml-auto flex items-center gap-2">
        <button
          className="toolbar-button"
          data-testid="explore-toolbar-graph-toggle"
          onClick={onToggleGraph}
          type="button"
        >
          {graphVisible ? "Panels" : "Graph"}
        </button>
        <button
          className="toolbar-button"
          data-testid="explore-toolbar-notebook-toggle"
          onClick={onToggleNotebook}
          type="button"
        >
          {tab.mode === "pause" && !tab.notebookVisible
            ? "Open notebook"
            : tab.notebookVisible
              ? "Hide notebook"
              : "Show notebook"}
        </button>
      </div>
    </div>
  );
}
