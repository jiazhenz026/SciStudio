/**
 * Workflow-only toolbar groups (Run/Pause/Stop/Reset + Delete/Reload/Note/
 * Group/View-source). Hidden when a file tab is active. Extracted in #1413.
 */
import {
  BoxSelect,
  Eye,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
  StickyNote,
  Trash2,
} from "lucide-react";

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
  onAddGroup: () => void;
  onViewSource?: () => void;
}

function ExecutionControls(props: WorkflowGroupsProps) {
  const { currentProject, workflowId, isRunning, onRun, onStop, onReset } = props;
  return (
    <div className="flex items-center gap-1">
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
        icon={Square}
        label="Stop"
        shortcut="Ctrl+."
        disabled={!workflowId}
        onClick={onStop}
      />
      <ToolbarButton icon={RotateCcw} label="Reset" disabled={!workflowId} onClick={onReset} />
    </div>
  );
}

function EditOperations(props: WorkflowGroupsProps) {
  const {
    currentProject,
    workflowId,
    selectedNodeId,
    onDelete,
    onReloadBlocks,
    onAddAnnotation,
    onAddGroup,
    onViewSource,
  } = props;
  return (
    <div className="flex items-center gap-1">
      <ToolbarButton icon={Trash2} label="Delete" disabled={!selectedNodeId} onClick={onDelete} />
      <ToolbarButton icon={RefreshCw} label="Reload" onClick={onReloadBlocks} />
      <ToolbarButton
        icon={StickyNote}
        label="Note"
        disabled={!currentProject}
        onClick={onAddAnnotation}
      />
      <ToolbarButton
        icon={BoxSelect}
        label="Group"
        disabled={!currentProject}
        onClick={onAddGroup}
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
      <Separator orientation="vertical" className="mx-1 h-8" />
      <ExecutionControls {...props} />
      <Separator orientation="vertical" className="mx-1 h-8" />
      <EditOperations {...props} />
    </>
  );
}
