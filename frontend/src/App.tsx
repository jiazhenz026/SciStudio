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
import type { AnyTab, FileTab } from "./store/types";
import type { ProjectResponse, WorkflowResponse } from "./types/api";

import { AppLevelMergeFlow } from "./App.parts/AppLevelMergeFlow";
import { InteractiveModals } from "./App.parts/InteractiveModals";
import { ProjectWorkspace } from "./App.parts/ProjectWorkspace";
import { useAppKeyboardShortcuts } from "./App.parts/useAppKeyboardShortcuts";
import { useAppLifecycleEffects } from "./App.parts/useAppLifecycleEffects";
import { useBottomPanelControls } from "./App.parts/useBottomPanelControls";
import { useCanvasHandlers } from "./App.parts/useCanvasHandlers";
import { useCanvasReadability } from "./App.parts/useCanvasReadability";
import { useFileTabsAutosave } from "./App.parts/useFileTabsAutosave";
import { usePromptInput } from "./App.parts/usePromptInput";
import { useBlockCatalogSync } from "./App.parts/useBlockCatalogSync";
import { useProjectActions } from "./App.parts/useProjectActions";
import { useWorkflowExecutionActions } from "./App.parts/useWorkflowExecutionActions";
import { useWorkflowSync } from "./App.parts/useWorkflowSync";

import { ProjectDialog } from "./components/ProjectDialog";
import { NewPlotDialog } from "./components/NewPlotDialog";
import { PromptDialog } from "./components/PromptDialog";
import { Toolbar } from "./components/Toolbar";
import { WelcomeScreen } from "./components/WelcomeScreen";
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

export default function App() {
  // --- Zustand selectors -------------------------------------------------
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
  const bumpProjectTreeRefresh = useAppStore((state) => state.bumpProjectTreeRefresh);

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
  // ADR-036 §3.10 / §3.7 — file tab actions.
  const saveFileTab = useAppStore((state) => state.saveFileTab);
  const updateFileTabContent = useAppStore((state) => state.updateFileTabContent);
  const openFileTab = useAppStore((state) => state.openFileTab);
  const openBlockSourceTab = useAppStore((state) => state.openBlockSourceTab);

  // ADR-036 §3.7 — derive the active tab + its kind for the toolbar swap.
  const activeTab = useMemo<AnyTab | null>(() => {
    const found = (tabs as AnyTab[]).find((t) => t.id === activeTabId);
    return found ?? null;
  }, [tabs, activeTabId]);
  const activeFileTab: FileTab | null = activeTab && activeTab.kind === "file" ? activeTab : null;
  const activeTabKind: "workflow" | "file" = activeFileTab ? "file" : "workflow";

  const [busy, setBusy] = useState(false);
  const [leftTab, setLeftTab] = useState<"blocks" | "project">("blocks");
  const [newPlotDialogOpen, setNewPlotDialogOpen] = useState(false);
  // Promise-based replacement for window.prompt (unsupported in Electron).
  const { promptRequest, promptInput, clearPrompt } = usePromptInput();

  // Bottom-panel imperative controls + cross-component callbacks.
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
  const readability = useCanvasReadability(handleNodeSelect); // ADR-050 §3 wiring.

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

  const workflowPayload = useMemo<WorkflowResponse>(
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

  // API-backed sync: project list refresh, block catalog refresh, workflow
  // save / save-as. Wrapped in a hook so identity stability is owned in one
  // place rather than being scattered across App.tsx.
  const { refreshProjects, refreshBlocks, saveWorkflow, saveWorkflowAs } = useWorkflowSync({
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

  // Project / workflow / file CRUD actions live in their own hook to keep
  // App.tsx focused on lifecycle + JSX.
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
    createNewNote,
    importWorkflow,
  } = projectActions;

  // Workflow execution callbacks (run / pause / resume / cancel / per-block).
  const {
    runWorkflow,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    startFromSelected,
    handleRunBlock,
    handleRestartBlock,
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

  // Canvas / toolbar handlers (palette add, edge connect, view source, save).
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

  // #2/#8/#9: keep the block catalog in sync with the canvas (custom / agent-added blocks).
  useBlockCatalogSync(refreshBlocks);

  // App-level lifecycle effects (boot, workflow autosave, tab snapshot sync).
  useAppLifecycleEffects({
    currentProject,
    workflowDirty,
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

  // ADR-036 §3.9 — per-tab autosave loop.
  useFileTabsAutosave({
    currentProject,
    tabs: tabs as AnyTab[],
    saveFileTab,
  });

  // Global keyboard shortcuts.
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
            onNewCustomBlock={
              currentProject
                ? () => {
                    void createNewCustomBlock();
                  }
                : undefined
            }
            onNewNote={
              currentProject
                ? () => {
                    void createNewNote();
                  }
                : undefined
            }
            onNewPlot={
              currentProject
                ? () => {
                    setNewPlotDialogOpen(true);
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
            onReloadBlocks={() => void refreshBlocks()}
            onStartFromSelected={() => void startFromSelected()}
            onAddAnnotation={() =>
              addAnnotationNode({ x: 150 + Math.random() * 200, y: 150 + Math.random() * 200 })
            }
            isRunning={isRunning}
          />

          <AppErrorBanner message={lastError} onDismiss={() => setLastError(null)} />

          {currentProject ? (
            <ProjectWorkspace
              currentProject={currentProject}
              leftTab={leftTab}
              onLeftTabChange={setLeftTab}
              blocks={blocks}
              paletteSearch={paletteSearch}
              setPaletteSearch={setPaletteSearch}
              onAddBlockFromPalette={handleAddBlockFromPalette}
              onReloadBlocks={() => void refreshBlocks()}
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
              onRestartBlock={handleRestartBlock}
              onSelectNode={handleNodeSelect}
              onUpdateNodeConfig={updateNodeConfig}
              onUpdateNodePosition={updateNodeLayout}
              onResizeNode={updateNodeSize}
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
          ) : (
            <div className="min-h-0 flex-1">
              <WelcomeScreen
                onDeleteProject={(projectId) => void deleteProject(projectId)}
                onNewProject={() => openProjectDialog("new")}
                onOpenProject={() => openProjectDialog("open")}
                onOpenRecent={(projectId) => void openProject(projectId)}
                recentProjects={recentProjects}
              />
            </div>
          )}

          <ProjectDialog
            description={projectDialog.description}
            mode={projectDialog.mode}
            name={projectDialog.name}
            onChange={updateProjectDialog}
            onClose={closeProjectDialog}
            onDeleteProject={(projectId) => void deleteProject(projectId)}
            onOpenRecent={(projectId) => void openProject(projectId)}
            onSubmit={() => void submitProjectDialog()}
            open={projectDialogOpen}
            path={projectDialog.path}
            recentProjects={recentProjects}
          />

          <NewPlotDialog
            onClose={() => setNewPlotDialogOpen(false)}
            onCreated={(created) => {
              bumpProjectTreeRefresh();
              openFileTab(created.script_path);
              setLastError(created.warnings.length > 0 ? created.warnings.join("\n") : null);
            }}
            open={Boolean(currentProject && newPlotDialogOpen)}
            saveWorkflow={saveWorkflow}
            selectedNodeId={selectedNodeId}
            workflowId={workflowId}
          />

          <PromptDialog request={promptRequest} onClose={clearPrompt} />

          {/* #591/#594: Interactive block modals. */}
          <InteractiveModals />

          {busy ? (
            <div className="fixed bottom-4 right-4 rounded-full bg-ink px-4 py-2 text-sm text-white">
              Working…
            </div>
          ) : null}

          {/* ADR-039 §3.5 (#975) — MergeFlow modal lives at App level. */}
          <AppLevelMergeFlow />
        </div>
      </TooltipProvider>
    </ReactFlowProvider>
  );
}
