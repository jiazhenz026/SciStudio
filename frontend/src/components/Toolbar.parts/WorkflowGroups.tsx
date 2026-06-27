/**
 * Workflow-only toolbar groups (Run/Pause/Stop/Reload + Note/View-source).
 * Hidden when a file tab is active. Extracted in #1413.
 */
import { Eye, Loader2, Play, RefreshCw, Square, StickyNote } from "lucide-react";
import { useEffect, useState } from "react";

import { Separator } from "@/components/ui/separator";

import type { ProjectResponse } from "../../types/api";
import { ToolbarButton } from "./ToolbarButton";

export interface WorkflowGroupsProps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  selectedNodeId: string | null;
  isRunning: boolean;
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
  const { currentProject, workflowId, isRunning, onRun, onStop, onReloadBlocks } = props;
  // #1789: the backend cancel blocks on the worker terminate grace period
  // (SIGTERM → wait → SIGKILL), so Stop looked dead for several seconds. Show an
  // optimistic "Stopping" state the instant it is clicked; clear it once the run
  // is no longer running (authoritative state arrives over the WS).
  const [isStopping, setIsStopping] = useState(false);
  useEffect(() => {
    if (!isRunning) setIsStopping(false);
  }, [isRunning]);
  const handleStop = () => {
    // Only enter the "Stopping" state when there is actually a live run to stop.
    // Clicking Stop on an already-finished run must not latch the spinner: the
    // clear effect above only fires on an isRunning true→false transition, so if
    // it was already false the state would never clear (stuck-Stopping bug).
    if (isRunning) setIsStopping(true);
    onStop();
  };
  // Belt-and-suspenders: never render "Stopping" once the run is no longer live.
  const showStopping = isStopping && isRunning;
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
      <ToolbarButton
        icon={showStopping ? Loader2 : Square}
        label={showStopping ? "Stopping" : "Stop"}
        shortcut="Ctrl+."
        disabled={!workflowId || showStopping}
        iconClassName={showStopping ? "animate-spin" : undefined}
        onClick={handleStop}
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
