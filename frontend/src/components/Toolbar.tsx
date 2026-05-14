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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import type { ProjectResponse } from "../types/api";

interface ToolbarProps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  workflowName: string;
  workflowDirty: boolean;
  selectedNodeId: string | null;
  wsConnected: boolean;
  sseConnected: boolean;
  recentProjects: ProjectResponse[];
  onNewProject: () => void;
  onOpenProject: () => void;
  onOpenRecent: (project: ProjectResponse) => void;
  onCloseProject: () => void;
  onNewWorkflow: () => void;
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

function StatusPill({
  connected,
  label,
}: {
  connected: boolean;
  label: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
        connected
          ? "bg-pine/15 text-pine"
          : "bg-stone-200 text-stone-500"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          connected ? "bg-pine" : "bg-stone-400"
        }`}
      />
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
          {shortcut ? (
            <span className="ml-2 text-xs opacity-70">{shortcut}</span>
          ) : null}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * ADR-036 §3.7 — file-tab toolbar (skeleton).
 *
 * SKELETON (S36): not rendered yet. Phase 2B (I36b) will:
 *   1. Add an ``activeTabKind: "workflow" | "file"`` prop to ToolbarProps
 *      (or read it from the store directly).
 *   2. In ``Toolbar``: ``if (activeTabKind === "file") return <FileToolbar .../>;``
 *      BEFORE the existing return statement.
 *   3. ``FileToolbar`` shows only New / Import / Save in v1 per ADR-036
 *      §3.7 ("v1 simplification: file-tab toolbar shows only New / Import
 *      / Save"). Find / Format / Goto-line are reached via Monaco's
 *      built-in keybindings (Ctrl+F, Shift+Alt+F).
 *
 * Test plan (vitest, must be added by I36b):
 *   - render with activeTabKind="file" → only New / Import / Save visible
 *   - render with activeTabKind="workflow" → existing button set unchanged
 *
 * References: ADR-036 §3.7 toolbar matrix.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function FileToolbar(_props: { onNew: () => void; onImport: () => void; onSave: () => void }) {
  // TODO(ADR-036 I36b): render New / Import / Save only.
  return null;
}

export function Toolbar(props: ToolbarProps) {
  // ADR-036 §3.7 — kind-switch scaffolding (skeleton, not yet routed).
  // Phase 2B (I36b) will read the active tab kind from the store and route
  // here before the existing return below:
  //
  //   const activeTab = useAppStore(state => state.tabs.find(t => t.id === state.activeTabId));
  //   if (activeTab?.kind === "file") {
  //     return <FileToolbar onNew={...} onImport={props.onImport} onSave={props.onSave} />;
  //   }
  //
  // Skeleton phase keeps existing buttons untouched per dispatch scope.

  const {
    currentProject,
    workflowId,
    workflowName,
    workflowDirty,
    selectedNodeId,
    wsConnected,
    sseConnected,
    recentProjects,
    onNewProject,
    onOpenProject,
    onOpenRecent,
    onCloseProject,
    onNewWorkflow,
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

  return (
    <TooltipProvider delayDuration={300}>
      <header className="flex items-center gap-3 border-b border-stone-200 bg-white/85 px-5 py-3 backdrop-blur">
        {/* Logo + Project Header */}
        <div className="flex items-center gap-3">
          <div className="rounded-[1.4rem] bg-ink px-4 py-2.5 text-stone-50">
            <p className="font-display text-lg leading-tight">SciEasy</p>
          </div>
          <div className="w-[200px] shrink-0">
            <p className="truncate font-display text-base leading-tight text-ink" title={currentProject?.name ?? undefined}>
              {currentProject?.name ?? "No project open"}
            </p>
            <p className="truncate text-xs text-stone-500" title={currentProject ? workflowName : undefined}>
              {currentProject
                ? (<>{workflowName}<span style={{ visibility: workflowDirty ? "visible" : "hidden" }}>{" *"}</span></>)
                : "Open or create a project"}
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
            <DropdownMenuItem
              disabled={!currentProject}
              onClick={onSave}
            >
              <Save className="size-4" />
              Save Workflow
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Recent Projects</DropdownMenuLabel>
            {recentProjects.length > 0 ? (
              recentProjects.slice(0, 5).map((project) => (
                <DropdownMenuItem
                  key={project.id}
                  onClick={() => onOpenRecent(project)}
                >
                  <span className="truncate">{project.name}</span>
                </DropdownMenuItem>
              ))
            ) : (
              <DropdownMenuItem disabled>
                <span className="text-stone-400">No recent projects</span>
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              disabled={!currentProject}
              onClick={onCloseProject}
            >
              <X className="size-4" />
              Close Project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Separator orientation="vertical" className="mx-1 h-8" />

        {/* Group 2: Workflow File Operations */}
        <div className="flex items-center gap-1">
          <ToolbarButton
            icon={FilePlus2}
            label="New"
            disabled={!currentProject}
            onClick={onNewWorkflow}
          />
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
        </div>

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
          <ToolbarButton
            icon={Pause}
            label="Pause"
            disabled={!workflowId}
            onClick={onPause}
          />
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
          <ToolbarButton
            icon={RefreshCw}
            label="Reload"
            onClick={onReloadBlocks}
          />
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
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Connection Status */}
        <div className="flex items-center gap-2">
          <StatusPill connected={wsConnected} label="WS" />
          <StatusPill connected={sseConnected} label="Logs" />
        </div>
      </header>
    </TooltipProvider>
  );
}
