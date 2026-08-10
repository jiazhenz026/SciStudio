// SciStudio App shell.
//
// Refactored under #1422 to delegate large concerns to focused modules in
// ./App.parts/:
//   - useAppKeyboardShortcuts — global Ctrl-S / Ctrl-Z / etc. listener,
//   - useFileTabsAutosave    — ADR-036 §3.9 per-tab debounced save,
//   - useProjectActions      — project / workflow / file CRUD callbacks,
//   - AppLevelMergeFlow      — ADR-039 §3.5 modal that survives project
//                              close,
//   - ProjectWorkspace       — three-column ResizablePanelGroup tree
//                              shown when a project is open,
//   - InteractiveModals      — DataRouter / PairEditor pause-prompts.
//
// Wave 1 (#1420 / #1421) discipline preserved:
//   - Every callback that is referenced by a useEffect or another
//     useCallback's dependency array stays wrapped in `useCallback` so its
//     identity is stable across renders.
//   - Every effect's dependency array is exhaustive (or carries the same
//     rationale comment + inline disable as the pre-split version).
//   - The hooks that originally lived under early returns now sit at the
//     top level of their own component (InlineTextInputField via the
//     BlockNode split; useAppKeyboardShortcuts here).

import { ReactFlowProvider } from "@xyflow/react";
import { useMemo, useState } from "react";

import { useLogStream } from "./hooks/useSSE";
import { useWorkflowWebSocket } from "./hooks/useWebSocket";
import { useAppStore } from "./store";
import type { AnyTab } from "./store/types";
import type { ProjectResponse, WorkflowResponse } from "./types/api";

import { AppLevelMergeFlow } from "./App.parts/AppLevelMergeFlow";
import { AppDialogs } from "./App.parts/AppDialogs";
import { InteractiveModals } from "./App.parts/InteractiveModals";
import { ProjectWorkspace, type LeftTab } from "./App.parts/ProjectWorkspace";
import { WelcomePane } from "./App.parts/WelcomePane";
import { useActiveTab } from "./App.parts/useActiveTab";
import { useAppKeyboardShortcuts } from "./App.parts/useAppKeyboardShortcuts";
import { useAppLifecycleEffects } from "./App.parts/useAppLifecycleEffects";
import { useBottomPanelControls } from "./App.parts/useBottomPanelControls";
import { useCanvasHandlers } from "./App.parts/useCanvasHandlers";
import { useCanvasReadability } from "./App.parts/useCanvasReadability";
import { useFileTabsAutosave } from "./App.parts/useFileTabsAutosave";
import { useLearningCenter } from "./App.parts/useLearningCenter";
import { usePromptInput } from "./App.parts/usePromptInput";
import { useBlockCatalogSync } from "./App.parts/useBlockCatalogSync";
import { useProjectActions } from "./App.parts/useProjectActions";
import { useWorkflowExecutionActions } from "./App.parts/useWorkflowExecutionActions";
import { useWorkflowSync } from "./App.parts/useWorkflowSync";

import { LearningCenter } from "./components/LearningCenter";
import { ActiveStep } from "./components/LearningCenter.parts/ActiveStep";
import { WorkImportOffer } from "./components/LearningCenter.parts/WorkImportOffer";
import { Toolbar } from "./components/Toolbar";
import { TooltipProvider } from "./components/ui/tooltip";

function emptyWorkflow(id = "main"): WorkflowResponse {
  return {
    id,
    version: "1.0.0",
    description: "",
    nodes: [],
    edges: [],
    metadata: {},
  };
}

/**
 * Close the active project: clear the project, reset the canvas/execution, and
 * drop the previous project's open workflow tabs (bug #5). Module-level so it
 * does not count against App()'s line budget.
 */
function closeCurrentProject(actions: {
  setCurrentProject: (project: ProjectResponse | null) => void;
  setWorkflow: (workflow: WorkflowResponse | null) => void;
  resetExecution: () => void;
}): void {
  actions.setCurrentProject(null);
  actions.setWorkflow(emptyWorkflow());
  actions.resetExecution();
  useAppStore.setState({ tabs: [], activeTabId: null });
}

/** Dismissable top-of-canvas error banner. Extracted to keep App() under the
 * max-lines-per-function lint limit. */
function AppErrorBanner({ message, onDismiss }: { message: string | null; onDismiss: () => void }) {
  if (!message) return null;
  return (
    <div
      className="flex items-start gap-3 border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700"
      data-testid="app-error-banner"
    >
      <span className="flex-1 whitespace-pre-wrap">{message}</span>
      <button
        type="button"
        aria-label="Dismiss error"
        title="Dismiss"
        data-testid="app-error-dismiss"
        className="shrink-0 rounded px-1.5 text-base leading-none text-red-500 hover:bg-red-100 hover:text-red-700"
        onClick={onDismiss}
      >
        ×
      </button>
    </div>
  );
}

/**
 * Global "still working" pill (#2019).
 *
 * Module-level for the same reason as `AppErrorBanner`: it keeps App() under
 * the max-lines-per-function limit.
 *
 * The indicator has to outrank every overlay. It previously carried no
 * z-index at all, so any modal — all of which are z-50 or z-[9999], most over
 * a backdrop blur — painted across it, and the one affordance telling the user
 * work was still in flight showed up blurred underneath the very dialog that
 * was waiting on that work. z-[10000] puts it above the topmost modal layer;
 * `pointer-events-none` keeps a purely informational pill from swallowing
 * clicks in the bottom-right corner now that it sits on top of everything.
 * `frontend/src/App.busyIndicator.test.tsx` guards the ordering.
 */
function GlobalBusyIndicator({ busy }: { busy: boolean }) {
  if (!busy) return null;
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-[10000] rounded-full bg-ink px-4 py-2 text-sm text-white"
      data-testid="global-busy-indicator"
      role="status"
    >
      Working…
    </div>
  );
}

function useWorkflowPayload({
  workflowDescription,
  workflowEdges,
  workflowId,
  workflowMetadata,
  workflowNodes,
  workflowVersion,
}: {
  workflowDescription: string;
  workflowEdges: WorkflowResponse["edges"];
  workflowId: string | null;
  workflowMetadata: WorkflowResponse["metadata"];
  workflowNodes: WorkflowResponse["nodes"];
  workflowVersion: string;
}): WorkflowResponse {
  return useMemo<WorkflowResponse>(
    () => ({
      id: workflowId ?? "main",
      version: workflowVersion,
      description: workflowDescription,
      metadata: workflowMetadata,
      nodes: workflowNodes,
      edges: workflowEdges,
    }),
    [
      workflowDescription,
      workflowEdges,
      workflowId,
      workflowMetadata,
      workflowNodes,
      workflowVersion,
    ],
  );
}

export default function App() {
  const currentProject = useAppStore((state) => state.currentProject);
  const recentProjects = useAppStore((state) => state.recentProjects);
  const projectDialogOpen = useAppStore((state) => state.projectDialogOpen);
  const projectDialog = useAppStore((state) => state.projectDialog);
  const setProjects = useAppStore((state) => state.setProjects);
  const setCurrentProject = useAppStore((state) => state.setCurrentProject);
  const openProjectDialog = useAppStore((state) => state.openProjectDialog);
  const closeProjectDialog = useAppStore((state) => state.closeProjectDialog);
  const updateProjectDialog = useAppStore((state) => state.updateProjectDialog);
  const workflowId = useAppStore((state) => state.workflowId);
  const workflowDescription = useAppStore((state) => state.workflowDescription);
  const workflowVersion = useAppStore((state) => state.workflowVersion);
  const workflowMetadata = useAppStore((state) => state.workflowMetadata);
  const workflowNodes = useAppStore((state) => state.workflowNodes);
  const workflowEdges = useAppStore((state) => state.workflowEdges);
  const workflowDirty = useAppStore((state) => state.workflowDirty);
  const workflowName = useAppStore((state) => state.workflowName);
  const setWorkflow = useAppStore((state) => state.setWorkflow);
  const addNode = useAppStore((state) => state.addNode);
  const updateNodeConfig = useAppStore((state) => state.updateNodeConfig);
  const updateNodeLayout = useAppStore((state) => state.updateNodeLayout);
  const updateNodeSize = useAppStore((state) => state.updateNodeSize);
  const connectNodes = useAppStore((state) => state.connectNodes);
  const removeNode = useAppStore((state) => state.removeNode);
  const removeEdge = useAppStore((state) => state.removeEdge);
  const addAnnotationNode = useAppStore((state) => state.addAnnotationNode);
  const markWorkflowSaved = useAppStore((state) => state.markWorkflowSaved);
  const workflowConflict = useAppStore((state) => state.workflowConflict);
  const resolveWorkflowConflict = useAppStore((state) => state.resolveWorkflowConflict);
  const undoWorkflow = useAppStore((state) => state.undoWorkflow);
  const redoWorkflow = useAppStore((state) => state.redoWorkflow);
  const blockStates = useAppStore((state) => state.blockStates);
  const blockOutputs = useAppStore((state) => state.blockOutputs);
  const blockErrors = useAppStore((state) => state.blockErrors);
  const blockErrorSummaries = useAppStore((state) => state.blockErrorSummaries);
  const logEntries = useAppStore((state) => state.logEntries);
  const isRunning = useAppStore((state) => state.isRunning);
  const resetExecution = useAppStore((state) => state.resetExecution);
  const selectedNodeId = useAppStore((state) => state.selectedNodeId);
  const activeBottomTab = useAppStore((state) => state.activeBottomTab);
  const unreadLogsCount = useAppStore((state) => state.unreadLogsCount);
  const lastError = useAppStore((state) => state.lastError);
  const minimapVisible = useAppStore((state) => state.minimapVisible);
  const setSelectedNodeId = useAppStore((state) => state.setSelectedNodeId);
  const setActiveBottomTab = useAppStore((state) => state.setActiveBottomTab);
  const togglePalette = useAppStore((state) => state.togglePalette);
  const togglePreview = useAppStore((state) => state.togglePreview);
  const toggleBottomPanel = useAppStore((state) => state.toggleBottomPanel);
  const bottomPanelPinned = useAppStore((state) => state.bottomPanelPinned);
  const toggleBottomPanelPinned = useAppStore((state) => state.toggleBottomPanelPinned);
  const toggleMinimap = useAppStore((state) => state.toggleMinimap);
  const setPanelSize = useAppStore((state) => state.setPanelSize);
  const setLastError = useAppStore((state) => state.setLastError);
  const blocks = useAppStore((state) => state.blocks);
  const blockSchemas = useAppStore((state) => state.blockSchemas);
  const paletteSearch = useAppStore((state) => state.paletteSearch);
  const setBlocks = useAppStore((state) => state.setBlocks);
  const setBlockSchema = useAppStore((state) => state.setBlockSchema);
  const setPaletteSearch = useAppStore((state) => state.setPaletteSearch);
  const tabs = useAppStore((state) => state.tabs);
  const activeTabId = useAppStore((state) => state.activeTabId);
  const openTab = useAppStore((state) => state.openTab);
  const switchTab = useAppStore((state) => state.switchTab);
  const closeTab = useAppStore((state) => state.closeTab);
  const syncActiveTab = useAppStore((state) => state.syncActiveTab);
  const saveFileTab = useAppStore((state) => state.saveFileTab);
  const updateFileTabContent = useAppStore((state) => state.updateFileTabContent);
  const openFileTab = useAppStore((state) => state.openFileTab);
  const openBlockSourceTab = useAppStore((state) => state.openBlockSourceTab);
  const { activeFileTab, activeTabKind } = useActiveTab(tabs as AnyTab[], activeTabId);
  const [busy, setBusy] = useState(false);
  const [leftTab, setLeftTab] = useState<LeftTab>("blocks");
  const openNewPlotPicker = useAppStore((state) => state.openNewPlotPicker);
  const { promptRequest, promptInput, clearPrompt } = usePromptInput();
  const {
    bottomPanelRef,
    handleCanvasPaneClick,
    handleNodeSelect,
    handleErrorClick,
    handleBottomTabChange,
  } = useBottomPanelControls({
    bottomPanelPinned,
    setSelectedNodeId,
    setActiveBottomTab,
  });
  const readability = useCanvasReadability(handleNodeSelect);
  const { connected: wsConnected, status: wsStatus } = useWorkflowWebSocket(
    Boolean(currentProject),
  );
  const { connected: sseConnected, status: sseStatus } = useLogStream(
    workflowId,
    activeBottomTab === "logs" ? selectedNodeId : null,
  );
  const selectedNode = useMemo(
    () => workflowNodes.find((node) => node.id === selectedNodeId) ?? null,
    [selectedNodeId, workflowNodes],
  );
  const selectedNodeLabel =
    blocks.find((block) => block.type_name === selectedNode?.block_type)?.name ??
    selectedNode?.block_type ??
    "";
  const workflowPayload = useWorkflowPayload({
    workflowDescription,
    workflowEdges,
    workflowId,
    workflowMetadata,
    workflowNodes,
    workflowVersion,
  });
  const { refreshProjects, refreshBlocks, reloadBlocks, saveWorkflow, saveWorkflowAs } =
    useWorkflowSync({
      currentProject,
      setCurrentProject,
      setBlocks,
      setBlockSchema,
      setProjects,
      markWorkflowSaved,
      setLastError,
      workflowPayload,
      workflowId,
    });
  const projectActions = useProjectActions({
    currentProject,
    setCurrentProject,
    setWorkflow,
    resetExecution,
    openTab,
    openFileTab,
    closeProjectDialog,
    setLastError,
    refreshProjects,
    refreshBlocks,
    setBusy,
    promptInput,
  });
  const {
    loadWorkflowById,
    openProject,
    submitProjectDialog,
    deleteProject,
    newWorkflow,
    createNewCustomBlock,
    createNewDataType,
    createNewNote,
    importWorkflow,
  } = projectActions;
  const {
    runWorkflow,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    startFromSelected,
    handleRunBlock,
  } = useWorkflowExecutionActions({
    currentProject,
    workflowId,
    selectedNodeId,
    saveWorkflow,
    setLastError,
    workflowPayloadId: workflowPayload.id,
    workflowNodes,
    blockSchemas,
  });
  const { handleAddBlockFromPalette, handleCanvasConnect, handleViewSource, handleSave } =
    useCanvasHandlers({
      currentProject,
      workflowId,
      workflowNodes,
      workflowEdges,
      activeFileTab,
      addNode,
      connectNodes,
      openFileTab,
      selectedNodeId,
      openBlockSourceTab,
      saveFileTab,
      saveWorkflow,
      setLastError,
      schemas: blockSchemas,
    });
  useBlockCatalogSync(refreshBlocks);
  useAppLifecycleEffects({
    currentProject,
    workflowDirty,
    workflowConflict,
    workflowPayload,
    refreshProjects,
    refreshBlocks,
    saveWorkflow,
    setBusy,
    setLastError,
    activeTabId,
    selectedNodeId,
    workflowDescription,
    workflowNodes,
    workflowEdges,
    syncActiveTab,
  });
  useFileTabsAutosave({
    currentProject,
    tabs: tabs as AnyTab[],
    saveFileTab,
  });

  /*
   * ADR-053 Learning Center (#2057) — start-up catalogue fetch, the FR-083
   * first-run landing, the reconnect refetch, and step-entry routing.
   */
  useLearningCenter({ wsConnected, setLeftTab, openProject });
  useAppKeyboardShortcuts({
    activeFileTab,
    cancelWorkflow,
    openProjectDialog,
    redoWorkflow,
    removeNode,
    runWorkflow,
    saveFileTab,
    saveWorkflow,
    saveWorkflowAs,
    selectedNodeId,
    setSelectedNodeId,
    toggleBottomPanel,
    toggleMinimap,
    togglePalette,
    togglePreview,
    undoWorkflow,
  });
  // The New-menu entries are project-scoped: `undefined` is what makes the
  // toolbar hide/disable them. ADR-053 FR-032 adds a third one, so the shape is
  // written once rather than three times.
  const whenProjectOpen = (run: () => Promise<void>) =>
    currentProject ? () => void run() : undefined;

  return (
    <ReactFlowProvider>
      <TooltipProvider delayDuration={300}>
        <div className="flex h-screen flex-col overflow-x-hidden bg-canvas text-stone-800">
          <Toolbar
            currentProject={currentProject}
            workflowId={workflowId}
            workflowName={workflowName}
            workflowDirty={workflowDirty}
            selectedNodeId={selectedNodeId}
            wsConnected={wsConnected}
            sseConnected={sseConnected}
            wsStatus={wsStatus}
            sseStatus={sseStatus}
            recentProjects={recentProjects}
            activeTabKind={activeTabKind}
            onNewProject={() => openProjectDialog("new", { path: projectDialog.path })}
            onOpenProject={() => openProjectDialog("open")}
            onOpenRecent={(project) => void openProject(project.id)}
            onCloseProject={() =>
              closeCurrentProject({ setCurrentProject, setWorkflow, resetExecution })
            }
            onNewWorkflow={newWorkflow}
            onNewCustomBlock={whenProjectOpen(createNewCustomBlock)}
            onNewDataType={whenProjectOpen(createNewDataType)}
            onNewNote={whenProjectOpen(createNewNote)}
            onNewPlot={
              currentProject
                ? () => {
                    void saveWorkflow().then(() => openNewPlotPicker());
                  }
                : undefined
            }
            onViewSource={currentProject && workflowId ? handleViewSource : undefined}
            onSave={handleSave}
            onSaveAs={() => void saveWorkflowAs()}
            onImport={() => void importWorkflow()}
            onRun={() => void runWorkflow()}
            onPause={() => void pauseWorkflow()}
            onResume={() => void resumeWorkflow()}
            onStop={() => void cancelWorkflow()}
            onReset={() => resetExecution()}
            onDelete={() => selectedNodeId && removeNode(selectedNodeId)}
            onReloadBlocks={() => void reloadBlocks()}
            onStartFromSelected={() => void startFromSelected()}
            onAddAnnotation={() =>
              addAnnotationNode({ x: 150 + Math.random() * 200, y: 150 + Math.random() * 200 })
            }
            isRunning={isRunning}
          />

          <AppErrorBanner message={lastError} onDismiss={() => setLastError(null)} />

          {/*
           * ADR-053 FR-089 — the active step sits in the layout, between the
           * toolbar and the workspace, so it never covers the canvas element it
           * is telling the user to act on. It renders nothing when no tutorial
           * is running.
           */}
          <ActiveStep />

          {currentProject ? (
            <>
              <ProjectWorkspace
                currentProject={currentProject}
                leftTab={leftTab}
                onLeftTabChange={setLeftTab}
                blocks={blocks}
                paletteSearch={paletteSearch}
                setPaletteSearch={setPaletteSearch}
                onAddBlockFromPalette={handleAddBlockFromPalette}
                onReloadBlocks={() => void reloadBlocks()}
                onLoadWorkflowById={(id, displayName) => void loadWorkflowById(id, displayName)}
                tabs={tabs as AnyTab[]}
                activeTabId={activeTabId}
                activeFileTab={activeFileTab}
                switchTab={switchTab}
                closeTab={closeTab}
                onNewWorkflowTab={newWorkflow}
                updateFileTabContent={updateFileTabContent}
                saveFileTab={saveFileTab}
                blockStates={blockStates}
                blockOutputs={blockOutputs}
                blockErrors={blockErrors}
                blockErrorSummaries={blockErrorSummaries}
                blockSchemas={blockSchemas}
                workflowNodes={workflowNodes}
                workflowEdges={workflowEdges}
                selectedNodeId={selectedNodeId}
                minimapVisible={minimapVisible}
                onCanvasAddNode={addNode}
                onCanvasConnect={handleCanvasConnect}
                onCanvasDeleteEdge={removeEdge}
                onCanvasDeleteNode={removeNode}
                onErrorClick={handleErrorClick}
                onCanvasPaneClick={handleCanvasPaneClick}
                onRunBlock={handleRunBlock}
                onSelectNode={handleNodeSelect}
                onUpdateNodeConfig={updateNodeConfig}
                onUpdateNodePosition={updateNodeLayout}
                onResizeNode={updateNodeSize}
                onOpenSubworkflow={projectActions.openSubworkflow}
                onLocateSubworkflow={projectActions.locateSubworkflow}
                readability={readability}
                bottomPanelRef={bottomPanelRef}
                bottomPanelPinned={bottomPanelPinned}
                toggleBottomPanelPinned={toggleBottomPanelPinned}
                activeBottomTab={activeBottomTab}
                onBottomTabChange={handleBottomTabChange}
                logEntries={logEntries}
                unreadLogsCount={unreadLogsCount}
                selectedNode={selectedNode}
                selectedSchema={selectedNode ? blockSchemas[selectedNode.block_type] : undefined}
                selectedNodeLabel={selectedNodeLabel}
                setPanelSize={setPanelSize}
              />
            </>
          ) : (
            <WelcomePane
              onDeleteProject={(projectId) => void deleteProject(projectId)}
              onNewProject={() => openProjectDialog("new")}
              onOpenProject={() => openProjectDialog("open")}
              onOpenRecent={(projectId) => void openProject(projectId)}
              recentProjects={recentProjects}
            />
          )}

          <AppDialogs
            busy={busy}
            projectDialog={projectDialog}
            projectDialogOpen={projectDialogOpen}
            promptRequest={promptRequest}
            recentProjects={recentProjects}
            workflowConflict={workflowConflict}
            onProjectDialogChange={updateProjectDialog}
            onProjectDialogClose={closeProjectDialog}
            onProjectDialogSubmit={() => void submitProjectDialog()}
            onDeleteProject={(projectId) => void deleteProject(projectId)}
            onOpenRecent={(projectId) => void openProject(projectId)}
            onPromptClose={clearPrompt}
            onResolveWorkflowConflict={resolveWorkflowConflict}
          />

          {/*
           * ADR-053 FR-079 — the single product behaviour progress drives.
           * Renders nothing unless the backend says the offer is still owed.
           */}
          <WorkImportOffer />

          {/* ADR-053 FR-082 … FR-088 — mounted once; the toolbar only opens it. */}
          <LearningCenter />

          <InteractiveModals />

          <GlobalBusyIndicator busy={busy} />

          <AppLevelMergeFlow />
        </div>
      </TooltipProvider>
    </ReactFlowProvider>
  );
}
