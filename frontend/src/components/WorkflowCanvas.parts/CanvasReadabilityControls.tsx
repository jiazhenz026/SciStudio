/**
 * Canvas readability controls (ADR-050 §3, FR-017/FR-020/FR-023).
 *
 * Renders the Focus toggle and the Tidy action near the ReactFlow controls
 * (not inside any node). When focus mode is active the panel also shows:
 *   - a visible exit affordance + a count of hidden nodes/edges (FR-017,
 *     ADR-050 §3.1);
 *   - a focus-scoped Tidy (default) AND a whole-workflow Tidy so the user can
 *     choose the layout scope (ADR-050 §3.2).
 *
 * Tidy is always an explicit user action (FR-023) — nothing here runs layout
 * automatically.
 */
import { Panel } from "@xyflow/react";
import { LayoutGrid, ScanSearch, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface CanvasReadabilityControlsProps {
  /** True when focus mode is currently active. */
  focusActive: boolean;
  /** True when entering focus mode is possible (a node is selected). */
  canFocus: boolean;
  /** Count of nodes hidden/dimmed by the active focus set (FR-017). */
  hiddenNodeCount: number;
  /** Count of edges hidden/dimmed by the active focus set. */
  hiddenEdgeCount: number;
  /** Enter focus mode around the current selection. */
  onEnterFocus: () => void;
  /** Exit focus mode (visible exit affordance). */
  onExitFocus: () => void;
  /**
   * Run tidy. When focus is active this lays out the focus scope; otherwise it
   * lays out the whole workflow.
   */
  onTidy: () => void;
  /** Run tidy on the whole workflow regardless of focus (focus-active only). */
  onTidyWhole: () => void;
}

export function CanvasReadabilityControls(props: CanvasReadabilityControlsProps) {
  const {
    focusActive,
    canFocus,
    hiddenNodeCount,
    hiddenEdgeCount,
    onEnterFocus,
    onExitFocus,
    onTidy,
    onTidyWhole,
  } = props;

  return (
    <Panel position="top-right" className="flex flex-col items-end gap-1.5">
      <div className="flex items-center gap-1.5 rounded-full border border-stone-200/70 bg-white/90 px-1.5 py-1 shadow-sm backdrop-blur">
        {focusActive ? (
          <Button
            type="button"
            variant="toolbar-dark"
            size="toolbar"
            onClick={onExitFocus}
            aria-label="Exit focus mode"
            title="Exit focus mode"
          >
            <X className="size-3.5" />
            <span>Exit focus</span>
          </Button>
        ) : (
          <Button
            type="button"
            variant="toolbar"
            size="toolbar"
            disabled={!canFocus}
            onClick={onEnterFocus}
            aria-label="Focus on selection"
            title={canFocus ? "Focus on selection" : "Select a node to focus"}
          >
            <ScanSearch className="size-3.5" />
            <span>Focus</span>
          </Button>
        )}

        <Button
          type="button"
          variant="toolbar"
          size="toolbar"
          onClick={onTidy}
          aria-label={focusActive ? "Tidy focused subgraph" : "Tidy layout"}
          title={focusActive ? "Tidy focused subgraph" : "Tidy layout"}
        >
          <LayoutGrid className="size-3.5" />
          <span>{focusActive ? "Tidy focus" : "Tidy"}</span>
        </Button>

        {focusActive ? (
          <Button
            type="button"
            variant="toolbar"
            size="toolbar"
            onClick={onTidyWhole}
            aria-label="Tidy whole workflow"
            title="Tidy whole workflow"
          >
            <span>Tidy all</span>
          </Button>
        ) : null}
      </div>

      {focusActive ? (
        <span
          className="rounded-full bg-ink/85 px-2 py-0.5 text-[0.7rem] text-stone-50 shadow-sm"
          aria-live="polite"
        >
          {hiddenNodeCount} node{hiddenNodeCount === 1 ? "" : "s"}, {hiddenEdgeCount} edge
          {hiddenEdgeCount === 1 ? "" : "s"} hidden
        </span>
      ) : null}
    </Panel>
  );
}
