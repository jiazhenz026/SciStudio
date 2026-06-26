/**
 * Workflow-only toolbar groups (Run/Pause/Stop/Reload + Note/View-source).
 * Hidden when a file tab is active. Extracted in #1413.
 */
import { Eye, Loader2, Play, RefreshCw, Square, StickyNote } from "lucide-react";

import { Separator } from "@/components/ui/separator";

import type { ProjectResponse } from "../../types/api";
import { ToolbarButton } from "./ToolbarButton";

export interface WorkflowGroupsProps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  selectedNodeId: string | null;
  isRunning: boolean;
  /** #1789: a cancel request is in flight; show immediate "Stopping…" feedback. */
  isStopping?: boolean;
  onRun: () => void;
  onPause: () => void;
  onStop: () => void;
  onReset: () => void;
  onDelete: () => void;
  onReloadBlocks: () => void;
  onAddAnnotation: () => void;
  onViewSource?: () => void;
}

function ExecutionControls(props: WorkflowGroupsProps) {
  const { currentProject, workflowId, isRunning, isStopping, onRun, onStop, onReloadBlocks } = props;
  return (
    <div className="flex shrink-0 items-center gap-1">
      <ToolbarButton
        icon={isRunning ? Loader2 : Play}
        label={isRunning ? "Running" : "Run"}
        shortcut="Ctrl+Enter"
        variant="toolbar-dark"
        disabled={!currentProject || isRunning}
        iconClassName={isRunning ? "animate-spin" : undefined}
        onClick={onRun}
      />
      {/* #1789: backend cancel blocks on the worker terminate grace period, so
          give the user immediate feedback instead of a dead button. */}
      <ToolbarButton
        icon={isStopping ? Loader2 : Square}
        label={isStopping ? "Stopping" : "Stop"}
        shortcut="Ctrl+."
        disabled={!workflowId || isStopping}
        iconClassName={isStopping ? "animate-spin" : undefined}
        onClick={onStop}
      />
      <ToolbarButton icon={RefreshCw} label="Reload" onClick={onReloadBlocks} />
    </div>
  );
}

function EditOperations(props: WorkflowGroupsProps) {
  const { currentProject, workflowId, onAddAnnotation, onViewSource } = props;
  return (
    <div className="flex shrink-0 items-center gap-1">
      <ToolbarButton
        icon={StickyNote}
        label="Note"
        disabled={!currentProject}
        onClick={onAddAnnotation}
      />
      {/* ADR-036 §3.4 (I36c) — "View source" opens a read-only Monaco tab. */}
      {onViewSource && workflowId ? (
        <ToolbarButton
          icon={Eye}
          label="View source"
          disabled={!currentProject}
          onClick={onViewSource}
        />
      ) : null}
    </div>
  );
}

export function WorkflowGroups(props: WorkflowGroupsProps) {
  return (
    <>
      <Separator orientation="vertical" className="mx-0 h-8 xl:mx-1" />
      <ExecutionControls {...props} />
      <Separator orientation="vertical" className="mx-0 h-8 xl:mx-1" />
      <EditOperations {...props} />
    </>
  );
}
