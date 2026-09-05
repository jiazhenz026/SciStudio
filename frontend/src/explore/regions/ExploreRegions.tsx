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

import type { ExploreSessionState, ExploreTab, PanelSlot } from "../../store/types";
import { ExplorePanelSlot, PauseControls } from "../PanelSlots";
import { VariableStrip } from "../VariableStrip";

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
    <Placeholder
      testId="explore-notebook-region"
      title="Notebook"
      owner="ADR-054 spec 4 T-004 to T-007 — NotebookShell"
    >
      <p className="mt-2 text-[11px] text-stone-400">
        {session ? `${session.cells.length} cells` : "opening…"} · {tab.notebookPath}
      </p>
    </Placeholder>
  );
}

/** FR-018 to FR-020 — the variable strip above the panel host (S4-A3, T-008). */
export function VariableStripRegion({ tab, session }: ExploreRegionProps) {
  return <VariableStrip tab={tab} session={session} />;
}

/** FR-019, FR-021 to FR-023 — one mounted panel host, bound to one name. */
export function PanelSlotRegion({ tab, session, slot }: PanelSlotRegionProps) {
  return <ExplorePanelSlot tab={tab} session={session} slot={slot} />;
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

/** FR-013, FR-014 — run-stale with its count, interrupt, restart, commit. */
export function ToolbarRunControls({ session }: ExploreRegionProps) {
  const stale = session?.cells.filter((cell) => cell.marks.includes("stale")).length ?? 0;
  return (
    <span
      className="text-[11px] text-stone-400"
      data-testid="explore-toolbar-run-controls"
      data-stale-count={stale}
    >
      ADR-054 spec 4 T-006/T-007 — run controls
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

/** FR-024, FR-025 — confirm and cancel, shown only in pause mode (S4-A3, T-010). */
export function ToolbarPauseControls({ tab, session }: ExploreRegionProps) {
  return <PauseControls tab={tab} session={session} />;
}
