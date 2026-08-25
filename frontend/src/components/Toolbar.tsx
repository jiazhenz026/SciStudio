import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { FolderInput, GraduationCap, Package } from "lucide-react";
import { useState } from "react";

import type { ConnectionStatus } from "../hooks/connectionState";
import { usePackageUpdates } from "../hooks/usePackageUpdates";
import { useAppStore } from "../store";
import { shouldShowUnfinishedTutorialDot } from "../store/learningCenterSlice";
import type { ProjectResponse } from "../types/api";
import { BringInMyWorkDialog } from "./BringInMyWorkDialog";
import { ENTRY_LABEL, NO_PROJECT_MESSAGE } from "./BringInMyWorkDialog.parts/copy";
import { LEARNING_CENTER_ENTRY_LABEL } from "./LearningCenter";
import { PackageManagerDialog } from "./PackageManagerDialog";
import { FileOperationsGroup } from "./Toolbar.parts/FileOperationsGroup";
import { ProjectHeader } from "./Toolbar.parts/ProjectHeader";
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
  /** ADR-053 FR-032 — optional. "New data type", the type-side twin. */
  onNewDataType?: () => void;
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
    onNewDataType,
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
  // #1784 — the WS/Logs connection pills were replaced by the Packages button.
  // The connection props stay on the contract (App.tsx still passes them) but
  // are no longer rendered here.
  void wsConnected;
  void sseConnected;
  void wsStatus;
  void sseStatus;
  const isFileTab = activeTabKind === "file";
  const [packageManagerOpen, setPackageManagerOpen] = useState(false);
  // ADR-053 spec 2 (#2001) — the dialog is mounted only while open so its
  // availability probe fires when the user asks for the feature, not on every
  // app start.
  const [bringInMyWorkOpen, setBringInMyWorkOpen] = useState(false);
  const { updateCount } = usePackageUpdates();
  /*
   * ADR-053 Learning Center (#2057) FR-082 — a PERMANENT entry, on the same
   * reasoning as "Bring in my work" beside it: nothing about progress decides
   * whether it can be reached. The panel itself is mounted once by `App.tsx`,
   * not here, because FR-083 also opens it as the first-run landing and two
   * mount points would be two panels.
   */
  const openLearningCenter = useAppStore((state) => state.openLearningCenter);
  const learningCenterCatalogue = useAppStore((state) => state.learningCenterCatalogue);
  const learningCenterFirstRunDismissed = useAppStore(
    (state) => state.learningCenterFirstRunDismissed,
  );
  const unfinishedTutorials = shouldShowUnfinishedTutorialDot({
    catalogue: learningCenterCatalogue,
    firstRunLandingDismissed: learningCenterFirstRunDismissed,
  });

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
          onNewDataType={onNewDataType}
          onNewNote={onNewNote}
          onNewPlot={onNewPlot}
          onInstallPackage={() => setPackageManagerOpen(true)}
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

        {/* #1784 — Packages: opens the in-app Package Manager. Badge marks
            available OTA updates found by the startup check. */}
        <div className="flex shrink-0 items-center gap-2">
          {/*
           * ADR-053 FR-082 — the Learning Center's permanent entry.
           *
           * FR-086 — the dot marks unfinished core work. It appears only once
           * the user has dismissed the first-run landing (pointing someone back
           * at the panel they are looking at says nothing), clears on its own
           * when the core group completes, and has no "dismiss forever": an
           * unfinished tutorial hidden permanently would be indistinguishable
           * from a finished one. Package groups never raise it (FR-080).
           */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                aria-label={LEARNING_CENTER_ENTRY_LABEL}
                className="relative inline-flex items-center gap-2 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100"
                data-testid="toolbar-learning-center"
                onClick={openLearningCenter}
                type="button"
              >
                <GraduationCap className="size-4" />
                <span className="hidden 2xl:inline">{LEARNING_CENTER_ENTRY_LABEL}</span>
                {unfinishedTutorials ? (
                  <span
                    aria-label="Unfinished tutorials"
                    className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full bg-ember"
                    data-testid="toolbar-learning-center-dot"
                  />
                ) : null}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {unfinishedTutorials
                ? `${LEARNING_CENTER_ENTRY_LABEL} — you have tutorials left to finish`
                : LEARNING_CENTER_ENTRY_LABEL}
            </TooltipContent>
          </Tooltip>
          {/*
           * ADR-053 spec 2 (#2001) / FR-001 — "Bring in my work" is a
           * PERMANENT toolbar entry. It is not gated on Learning Center
           * progress, project count, or elapsed time: ADR-053 §4.2's threshold
           * governs when the product VOLUNTEERS this capability, never whether
           * it can be reached. It is also rendered for both tab kinds, since a
           * user editing a file has the same existing analysis to carry across
           * as one looking at a canvas.
           *
           * FR-002 — enabled when a project is open, disabled otherwise,
           * because a session writes its blocks into a project.
           */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                aria-label={ENTRY_LABEL}
                className="relative inline-flex items-center gap-2 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-50 disabled:hover:bg-transparent"
                data-testid="toolbar-bring-in-my-work"
                /* ADR-053 FR-011 (#2061) — the `bring_in_my_work_button`
                 * highlight target: the work-import level ends by pointing
                 * at the permanent entry the reader will use with their own
                 * data. */
                data-tutorial-target="bring_in_my_work_button"
                disabled={!currentProject}
                onClick={() => setBringInMyWorkOpen(true)}
                type="button"
              >
                <FolderInput className="size-4" />
                <span className="hidden 2xl:inline">{ENTRY_LABEL}</span>
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {currentProject
                ? `${ENTRY_LABEL} — carry an analysis you already have into SciStudio`
                : `${ENTRY_LABEL} — ${NO_PROJECT_MESSAGE}`}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                aria-label="Packages"
                className="relative inline-flex items-center gap-2 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100"
                onClick={() => setPackageManagerOpen(true)}
                type="button"
              >
                <Package className="size-4" />
                <span className="hidden xl:inline">Packages</span>
                {updateCount > 0 ? (
                  <span
                    aria-label={`${updateCount} package update${updateCount === 1 ? "" : "s"} available`}
                    className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-pine px-1 text-[10px] font-semibold text-white"
                  >
                    {updateCount}
                  </span>
                ) : null}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {updateCount > 0
                ? `Packages — ${updateCount} update${updateCount === 1 ? "" : "s"} available`
                : "Packages"}
            </TooltipContent>
          </Tooltip>
        </div>
      </header>
      <PackageManagerDialog
        onClose={() => setPackageManagerOpen(false)}
        open={packageManagerOpen}
      />
      {bringInMyWorkOpen ? (
        <BringInMyWorkDialog onClose={() => setBringInMyWorkOpen(false)} />
      ) : null}
    </TooltipProvider>
  );
}
