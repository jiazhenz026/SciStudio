import {
  Play,
  Pause,
  Square,
  RotateCcw,
  Trash2,
  RefreshCw,
  FolderOpen,
  Save,
  Import,
  ChevronDown,
  Plus,
  X,
  StickyNote,
  BoxSelect,
  FilePlus2,
  SaveAll,
  Loader2,
  Eye,
  FileCode2,
  FileText,
  Workflow,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

import type { ProjectResponse } from "../types/api";

// ADR-039 §3.5 (#972) — Git affordances (BranchPicker / GitStatusBadge /
// CommitDialog / MergeFlow) used to mount here. They now live in the
// dedicated Git BottomPanel tab (`components/Git/GitTab.tsx`) so the
// top toolbar no longer overflows on narrow viewports and
// GitHistoryList is reachable. The Toolbar is back to its pre-D39-2.3b
// non-Git shape.

interface ToolbarProps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  workflowName: string;
  workflowDirty: boolean;
  selectedNodeId: string | null;
  wsConnected: boolean;
  sseConnected: boolean;
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
  /**
   * ADR-036 §3.7 / §3.12 — "New custom block" menu action. Optional; when
   * absent the menu item is disabled.
   */
  onNewCustomBlock?: () => void;
  /**
   * ADR-036 §3.7 / §3.12 — "New note" (markdown) menu action. Optional;
   * when absent the menu item is disabled.
   */
  onNewNote?: () => void;
  /**
   * ADR-036 §3.4 — "View source" toolbar button on workflow tabs. Optional;
   * when absent the button is hidden. Implementations should open a
   * read-only ``kind=file`` tab on ``workflows/<workflowId>.yaml``.
   */
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
  onAddGroup: () => void;
  isRunning: boolean;
}

function StatusPill({ connected, label }: { connected: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
        connected ? "bg-pine/15 text-pine" : "bg-stone-200 text-stone-500"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${connected ? "bg-pine" : "bg-stone-400"}`} />
      {label}
    </span>
  );
}

function ToolbarButton({
  icon: Icon,
  label,
  shortcut,
  disabled,
  variant = "toolbar",
  iconClassName,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  variant?: "toolbar" | "toolbar-dark";
  iconClassName?: string;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={variant}
          size="toolbar"
          disabled={disabled}
          onClick={onClick}
          type="button"
        >
          <Icon className={iconClassName ? `size-3.5 ${iconClassName}` : "size-3.5"} />
          {label}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p>
          {label}
          {shortcut ? <span className="ml-2 text-xs opacity-70">{shortcut}</span> : null}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

export function Toolbar(props: ToolbarProps) {
  // ADR-036 §3.7 — kind-swap. When the active tab is a file (Monaco
  // editor), most workflow-only buttons are hidden and only
  // New / Import / Save remain. v1 simplification: Find / Format /
  // Goto-line are reached via Monaco's built-in keybindings (Ctrl+F,
  // Shift+Alt+F) without dedicated toolbar buttons.
  const {
    currentProject,
    workflowId,
    workflowName,
    workflowDirty,
    selectedNodeId,
    wsConnected,
    sseConnected,
    recentProjects,
    activeTabKind = "workflow",
    onNewProject,
    onOpenProject,
    onOpenRecent,
    onCloseProject,
    onNewWorkflow,
    onNewCustomBlock,
    onNewNote,
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
    onAddGroup,
    isRunning,
  } = props;
  // Reference to silence unused-var warnings for handlers reserved for
  // workflow-only groups when the file toolbar is rendered. They remain
  // typed as required props so App.tsx contracts don't change.
  void onResume;
  void onStartFromSelected;
  const isFileTab = activeTabKind === "file";

  return (
    <TooltipProvider delayDuration={300}>
      <header
        // ADR-039 §3.5 (#972) — Git affordances moved to the Git
        // BottomPanel tab; the toolbar no longer overflows. Keep
        // `overflow-x-auto` as a defensive fallback for future button
        // additions but the normal case is a single non-scrolling row.
        className="flex items-center gap-3 overflow-x-auto border-b border-stone-200 bg-white/85 px-5 py-3 backdrop-blur"
      >
        {/* Logo + Project Header */}
        <div className="flex items-center gap-3">
          <div className="rounded-[1.4rem] bg-ink px-4 py-2.5 text-stone-50">
            <p className="font-display text-lg leading-tight">SciStudio</p>
          </div>
          <div className="w-[200px] shrink-0">
            <p
              className="truncate font-display text-base leading-tight text-ink"
              title={currentProject?.name ?? undefined}
            >
              {currentProject?.name ?? "No project open"}
            </p>
            <p
              className="truncate text-xs text-stone-500"
              title={currentProject ? workflowName : undefined}
            >
              {currentProject ? (
                <>
                  {workflowName}
                  <span style={{ visibility: workflowDirty ? "visible" : "hidden" }}>{" *"}</span>
                </>
              ) : (
                "Open or create a project"
              )}
            </p>
          </div>
        </div>

        <Separator orientation="vertical" className="mx-1 h-8" />

        {/* Group 1: Projects Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="toolbar" size="toolbar" type="button">
              <FolderOpen className="size-3.5" />
              Projects
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="max-h-96 w-56 overflow-y-auto">
            <DropdownMenuItem onClick={onNewProject}>
              <Plus className="size-4" />
              New Project...
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onOpenProject}>
              <FolderOpen className="size-4" />
              Open Project...
            </DropdownMenuItem>
            <DropdownMenuItem disabled={!currentProject} onClick={onSave}>
              <Save className="size-4" />
              Save Workflow
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Recent Projects</DropdownMenuLabel>
            {recentProjects.length > 0 ? (
              recentProjects.slice(0, 5).map((project) => (
                <DropdownMenuItem key={project.id} onClick={() => onOpenRecent(project)}>
                  <span className="truncate">{project.name}</span>
                </DropdownMenuItem>
              ))
            ) : (
              <DropdownMenuItem disabled>
                <span className="text-stone-400">No recent projects</span>
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={!currentProject} onClick={onCloseProject}>
              <X className="size-4" />
              Close Project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Separator orientation="vertical" className="mx-1 h-8" />

        {/* Group 2: File Operations (shared across tab kinds) */}
        <div className="flex items-center gap-1">
          {/*
           * ADR-036 §3.7 / §3.12 (I36c) — "New" is a constrained
           * three-item menu: workflow / custom block / note. No "New
           * arbitrary file" entry; users with one-off needs use the
           * project tree.
           */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="toolbar" size="toolbar" disabled={!currentProject} type="button">
                <FilePlus2 className="size-3.5" />
                New
                <ChevronDown className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={onNewWorkflow} disabled={!currentProject}>
                <Workflow className="size-4" />
                New workflow
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={onNewCustomBlock}
                disabled={!currentProject || !onNewCustomBlock}
              >
                <FileCode2 className="size-4" />
                New custom block
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onNewNote} disabled={!currentProject || !onNewNote}>
                <FileText className="size-4" />
                New note
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <ToolbarButton
            icon={Import}
            label="Import"
            disabled={!currentProject}
            onClick={onImport}
          />
          <ToolbarButton
            icon={Save}
            label="Save"
            shortcut="Ctrl+S"
            disabled={!currentProject}
            onClick={onSave}
          />
          {/*
           * Save-As dropdown: only meaningful for workflow tabs in v1.
           * File tabs save to a fixed path (their `tab.filePath`); a "save
           * to a different path" affordance is out of scope per ADR-036
           * §3.9 ("rely on auto-save"). Hide for file tabs.
           */}
          {!isFileTab && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="toolbar"
                  size="toolbar"
                  disabled={!currentProject}
                  type="button"
                  className="px-1"
                >
                  <ChevronDown className="size-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onClick={onSave}>
                  <Save className="size-4" />
                  Save
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onSaveAs}>
                  <SaveAll className="size-4" />
                  Save As...
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/*
         * Workflow-only groups (Run/Pause/Stop/Reset, Delete/Reload/Note/Group)
         * are hidden when a file tab is active. ADR-036 §3.7 toolbar matrix.
         */}
        {!isFileTab && (
          <>
            <Separator orientation="vertical" className="mx-1 h-8" />

            {/* Group 3: Execution Controls */}
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
              <ToolbarButton icon={Pause} label="Pause" disabled={!workflowId} onClick={onPause} />
              <ToolbarButton
                icon={Square}
                label="Stop"
                shortcut="Ctrl+."
                disabled={!workflowId}
                onClick={onStop}
              />
              <ToolbarButton
                icon={RotateCcw}
                label="Reset"
                disabled={!workflowId}
                onClick={onReset}
              />
            </div>

            <Separator orientation="vertical" className="mx-1 h-8" />

            {/* Group 4: Edit Operations */}
            <div className="flex items-center gap-1">
              <ToolbarButton
                icon={Trash2}
                label="Delete"
                disabled={!selectedNodeId}
                onClick={onDelete}
              />
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
              {/*
               * ADR-036 §3.4 (I36c) — "View source" opens a read-only
               * Monaco tab on the active workflow's YAML. The tab id is
               * prefixed ``source:`` so re-clicking focuses the existing
               * source view instead of opening a duplicate (dedup by
               * prefix lives in tabSlice.openFileTab).
               */}
              {onViewSource && workflowId ? (
                <ToolbarButton
                  icon={Eye}
                  label="View source"
                  disabled={!currentProject}
                  onClick={onViewSource}
                />
              ) : null}
            </div>
          </>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Connection Status */}
        <div className="flex shrink-0 items-center gap-2">
          <StatusPill connected={wsConnected} label="WS" />
          <StatusPill connected={sseConnected} label="Logs" />
        </div>
      </header>
    </TooltipProvider>
  );
}
