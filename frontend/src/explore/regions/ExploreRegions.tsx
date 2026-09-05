/**
 * ADR-054 spec 4 (T-002) — the Explore tab's region contract.
 *
 * `ExploreTab.tsx` owns the arrangement; the contents of each region belong to
 * whoever owns that part of the spec. This module is the seam between them:
 * one placeholder component per region, each with the props the real component
 * takes, so an owner replaces a body here rather than restructuring a layout
 * they do not own.
 *
 * **How to take a region over.** Keep the exported name and the props; replace
 * the body with your component. Every region is handed the tab and the session
 * — the session is `undefined` until the open lands, and rendering that case is
 * part of the region's job, because the tab is on screen before the runtime has
 * answered.
 *
 *   - `NotebookRegion`        — ADR-054 spec 4 T-004 to T-007 (S4-A2).
 *   - `ToolbarRunControls`    — T-006, T-007 (S4-A2).
 *   - `VariableStripRegion`   — T-008 (S4-A3).
 *   - `PanelSlotRegion`       — T-009 (S4-A3); one instance per open panel.
 *   - `ToolbarPauseControls`  — T-011 (S4-A3).
 *   - `ToolbarKernelControls` — T-012, T-013 (S4-A4).
 *   - `GraphViewRegion`       — T-014 (S4-A4).
 *
 * FR-034 applies here as much as in the slice: a region draws what the session
 * says and sends commands through `lib/api/explore.ts`. None of them may
 * compute a mark, a kernel state, or a binding.
 */

import { useCallback, useState } from "react";

import { exploreApi } from "../../lib/api/explore";
import { logger } from "../../lib/logger";
import { useAppStore } from "../../store";
import type { ExploreSessionState, ExploreTab, PanelSlot } from "../../store/types";
import { NotebookShell } from "../NotebookShell";

/** What every region is handed. */
export interface ExploreRegionProps {
  /** The tab this region is rendered in. */
  tab: ExploreTab;
  /**
   * The session, or `undefined` while the open or restore is in flight.
   *
   * Not narrowed away: the tab is on screen before the runtime answers, and a
   * region that assumed a session would render nothing for that whole window.
   */
  session: ExploreSessionState | undefined;
}

/** One mounted panel in the centre. `PanelSlotRegion` gets one per open panel. */
export interface PanelSlotRegionProps extends ExploreRegionProps {
  /** The slot this instance hosts, from `ExploreSessionState.panels`. */
  slot: PanelSlot;
}

function Placeholder({
  testId,
  title,
  owner,
  children,
}: {
  testId: string;
  title: string;
  owner: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="flex h-full min-h-0 flex-col rounded border border-dashed border-stone-300 bg-white/40 p-3 text-xs text-stone-500"
      data-testid={testId}
    >
      <p className="font-medium text-stone-600">{title}</p>
      <p className="mt-1 text-[11px] text-stone-400">{owner}</p>
      {children}
    </div>
  );
}

/**
 * FR-008 to FR-013, FR-017 — the notebook shell.
 *
 * Rendered in the right column (FR-005), not in the centre, which is why
 * `ExploreTab.tsx` exports `ExploreNotebookPane` separately from the tab body.
 */
export function NotebookRegion({ tab, session }: ExploreRegionProps) {
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="explore-notebook-region">
      <NotebookShell session={session} tab={tab} />
    </div>
  );
}

/** FR-018 to FR-020 — the variable strip above the panel host. */
export function VariableStripRegion({ session }: ExploreRegionProps) {
  return (
    <div
      className="flex items-center gap-2 overflow-x-auto rounded border border-dashed border-stone-300 bg-white/40 px-3 py-2 text-xs text-stone-500 scrollbar-thin"
      data-testid="explore-variable-strip-region"
    >
      <span className="font-medium text-stone-600">Variables</span>
      <span className="text-[11px] text-stone-400">
        ADR-054 spec 4 T-008 — VariableStrip ({session?.bindings.length ?? 0})
      </span>
    </div>
  );
}

/** FR-019, FR-021 to FR-023 — one mounted panel host, bound to one name. */
export function PanelSlotRegion({ slot }: PanelSlotRegionProps) {
  return (
    <Placeholder
      testId={`explore-panel-slot-${slot.panelId}`}
      title={slot.boundName}
      owner="ADR-054 spec 4 T-009 — PanelSlots"
    />
  );
}

/** FR-032 — the secondary dependency-graph view. */
export function GraphViewRegion({ session }: ExploreRegionProps) {
  return (
    <Placeholder
      testId="explore-graph-region"
      title="Dependency graph"
      owner="ADR-054 spec 4 T-014 — GraphView"
    >
      <p className="mt-2 text-[11px] text-stone-400">
        {session?.graph ? `${session.graph.edges.length} edges` : "no analysis yet"}
      </p>
    </Placeholder>
  );
}

/**
 * FR-013, FR-014, FR-016 — run-stale with its count, interrupt, restart, commit
 * (ADR-054 spec 4 T-006, T-007).
 *
 * Every control here sends exactly one command and shows nothing until the
 * runtime answers. The stale count is a count of the marks the runtime sent, not
 * a judgement about which cells look stale (FR-034): run-stale is offered when
 * the runtime has marked something and refused when it has not, so the button
 * can never ask for a run the runtime does not think is needed.
 *
 * Interrupt, restart and commit write nothing into the slice at all — the
 * runtime publishes `kernel_state` and `commit_recorded` for those, and a
 * command reflected before its event is exactly what FR-034 forbids. Only the
 * run controls apply their response, because a queued request has no event of
 * its own and `applyExploreRunRequests` is the slice's documented door for it.
 */
export function ToolbarRunControls({ session }: ExploreRegionProps) {
  const applyExploreRunRequests = useAppStore((state) => state.applyExploreRunRequests);
  const [error, setError] = useState<string | null>(null);

  const sessionId = session?.sessionId ?? "";
  const disabled = sessionId === "";
  const stale = session?.cells.filter((cell) => cell.marks.includes("stale")).length ?? 0;
  // FR-016 — the runtime reports a dead kernel and a retirement separately, and
  // either is a reason to offer a restart. Neither is inferred here.
  const needsRestart = session?.kernel.needsRestart === true || session?.kernel.state === "dead";

  const send = useCallback(async (what: string, command: () => Promise<void>) => {
    setError(null);
    try {
      await command();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      logger.error(`explore: ${what}`, { error: message });
      setError(`${what}: ${message}`);
    }
  }, []);

  const onRunStale = () =>
    void send("Running the stale cells failed", async () => {
      const response = await exploreApi.runExploreStale(sessionId);
      applyExploreRunRequests(sessionId, response.requests);
    });

  return (
    <span
      className="flex flex-wrap items-center gap-1 text-[11px]"
      data-testid="explore-toolbar-run-controls"
      data-stale-count={stale}
    >
      <button
        className="toolbar-button"
        data-testid="explore-run-stale"
        disabled={disabled || stale === 0}
        onClick={onRunStale}
        type="button"
      >
        Run stale ({stale})
      </button>
      <button
        className="toolbar-button"
        data-testid="explore-interrupt"
        disabled={disabled}
        onClick={() =>
          void send("Interrupting the kernel failed", async () => {
            await exploreApi.interruptExploreSession(sessionId);
          })
        }
        type="button"
      >
        Interrupt
      </button>
      <button
        className={`toolbar-button ${needsRestart ? "border-amber-400 text-amber-800" : ""}`}
        data-testid="explore-restart"
        disabled={disabled}
        onClick={() =>
          void send("Restarting the kernel failed", async () => {
            await exploreApi.restartExploreSession(sessionId);
          })
        }
        type="button"
      >
        Restart
      </button>
      <button
        className="toolbar-button"
        data-testid="explore-commit"
        disabled={disabled}
        onClick={() =>
          void send("Committing the notebook failed", async () => {
            await exploreApi.commitExploreSession(sessionId);
          })
        }
        type="button"
      >
        Commit
      </button>
      {needsRestart ? (
        <span className="text-amber-800" data-testid="explore-kernel-restart-offer">
          This kernel needs a restart.
        </span>
      ) : null}
      {error ? (
        <span className="text-red-700" data-testid="explore-run-controls-error">
          {error}
        </span>
      ) : null}
    </span>
  );
}

/** FR-014 to FR-016, FR-028 — the kernel list and the package control. */
export function ToolbarKernelControls(_props: ExploreRegionProps) {
  return (
    <span className="text-[11px] text-stone-400" data-testid="explore-toolbar-kernel-controls">
      ADR-054 spec 4 T-012/T-013 — kernel list, package
    </span>
  );
}

/** FR-024, FR-025 — confirm and cancel, shown only in pause mode. */
export function ToolbarPauseControls(_props: ExploreRegionProps) {
  return (
    <span className="text-[11px] text-stone-400" data-testid="explore-toolbar-pause-controls">
      ADR-054 spec 4 T-011 — confirm, cancel
    </span>
  );
}
