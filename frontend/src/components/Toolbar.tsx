import { Separator } from "@/components/ui/separator";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useState } from "react";

import type { ConnectionStatus } from "../hooks/connectionState";
import type { ProjectResponse } from "../types/api";
import { PackageInstallerDialog } from "./PackageInstallerDialog";
import { FileOperationsGroup } from "./Toolbar.parts/FileOperationsGroup";
import { ProjectHeader, StatusPill } from "./Toolbar.parts/ProjectHeader";
import { ProjectsDropdown } from "./Toolbar.parts/ProjectsDropdown";
import { WorkflowGroups } from "./Toolbar.parts/WorkflowGroups";

// ADR-039 §3.5 (#972) — Git affordances (BranchPicker / GitStatusBadge /
// CommitDialog / MergeFlow) used to mount here. They now live in the
// dedicated Git BottomPanel tab (`components/Git/GitTab.tsx`) so the
// top toolbar no longer overflows on narrow viewports.

interface ToolbarProps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  workflowName: string;
  workflowDirty: boolean;
  selectedNodeId: string | null;
  wsConnected: boolean;
  sseConnected: boolean;
  /** #177: full connection lifecycle for the status pills (optional;
   *  falls back to the boolean when absent). */
  wsStatus?: ConnectionStatus;
  sseStatus?: ConnectionStatus;
  recentProjects: ProjectResponse[];
  /**
   * ADR-036 §3.7 — discriminator that drives the toolbar's kind-swap.
   * "workflow" (default) → existing canvas-oriented buttons.
   * "file"              → file-tab toolbar (New / Import / Save only in v1).
   */
  activeTabKind?: "workflow" | "file";
  onNewProject: () => void;
  onOpenProject: () => void;
  onOpenRecent: (project: ProjectResponse) => void;
  onCloseProject: () => void;
  onNewWorkflow: () => void;
  /** ADR-036 §3.7 / §3.12 — optional. */
  onNewCustomBlock?: () => void;
  /** ADR-036 §3.7 / §3.12 — optional. */
  onNewNote?: () => void;
  onNewPlot?: () => void;
  /** ADR-036 §3.4 — optional. Opens read-only YAML view of active workflow. */
  onViewSource?: () => void;
  onSave: () => void;
  onSaveAs: () => void;
  onImport: () => void;
  onRun: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onReset: () => void;
  onDelete: () => void;
  onReloadBlocks: () => void;
  onStartFromSelected: () => void;
  onAddAnnotation: () => void;
  isRunning: boolean;
}

export function Toolbar(props: ToolbarProps) {
  // ADR-036 §3.7 — kind-swap. When the active tab is a file (Monaco editor),
  // workflow-only buttons hide. v1: Find / Format / Goto-line are reached
  // via Monaco's built-in keybindings (Ctrl+F, Shift+Alt+F).
  const {
    currentProject,
    workflowId,
    workflowName,
    workflowDirty,
    selectedNodeId,
    wsConnected,
    sseConnected,
    wsStatus,
    sseStatus,
    recentProjects,
    activeTabKind = "workflow",
    onNewProject,
    onOpenProject,
    onOpenRecent,
    onCloseProject,
    onNewWorkflow,
    onNewCustomBlock,
    onNewNote,
    onNewPlot,
    onViewSource,
    onSave,
    onSaveAs,
    onImport,
    onRun,
    onPause,
    onResume,
    onStop,
    onReset,
    onDelete,
    onReloadBlocks,
    onStartFromSelected,
    onAddAnnotation,
    isRunning,
  } = props;
  // Reference to silence unused-var warnings for handlers reserved for
  // workflow-only groups when the file toolbar is rendered. They remain
  // typed as required props so App.tsx contracts don't change.
  void onResume;
  void onStartFromSelected;
  const isFileTab = activeTabKind === "file";
  const [packageInstallerOpen, setPackageInstallerOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={300}>
      <header
        // ADR-039 §3.5 (#972) — Git affordances moved to the Git tab; the
        // toolbar no longer overflows. `overflow-x-auto` is kept as a
        // defensive fallback.
        className="flex min-w-0 items-center gap-2 overflow-hidden border-b border-stone-200 bg-white/85 px-3 py-3 backdrop-blur xl:gap-3 xl:px-5"
      >
        <ProjectHeader
          currentProject={currentProject}
          workflowName={workflowName}
          workflowDirty={workflowDirty}
        />

        <Separator orientation="vertical" className="mx-0 h-8 xl:mx-1" />

        <ProjectsDropdown
          currentProject={currentProject}
          recentProjects={recentProjects}
          onNewProject={onNewProject}
          onOpenProject={onOpenProject}
          onSave={onSave}
          onOpenRecent={onOpenRecent}
          onCloseProject={onCloseProject}
        />

        <Separator orientation="vertical" className="mx-0 h-8 xl:mx-1" />

        <FileOperationsGroup
          currentProject={currentProject}
          isFileTab={isFileTab}
          onNewWorkflow={onNewWorkflow}
          onNewCustomBlock={onNewCustomBlock}
          onNewNote={onNewNote}
          onNewPlot={onNewPlot}
          onInstallPackage={() => setPackageInstallerOpen(true)}
          onImport={onImport}
          onSave={onSave}
          onSaveAs={onSaveAs}
        />

        {!isFileTab && (
          <WorkflowGroups
            currentProject={currentProject}
            workflowId={workflowId}
            selectedNodeId={selectedNodeId}
            isRunning={isRunning}
            onRun={onRun}
            onPause={onPause}
            onStop={onStop}
            onReset={onReset}
            onDelete={onDelete}
            onReloadBlocks={onReloadBlocks}
            onAddAnnotation={onAddAnnotation}
            onViewSource={onViewSource}
          />
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Connection Status */}
        <div className="flex shrink-0 items-center gap-2">
          <StatusPill connected={wsConnected} status={wsStatus} label="WS" />
          <StatusPill connected={sseConnected} status={sseStatus} label="Logs" />
        </div>
      </header>
      <PackageInstallerDialog
        onClose={() => setPackageInstallerOpen(false)}
        open={packageInstallerOpen}
      />
    </TooltipProvider>
  );
}
