import { ReactFlowProvider } from "@xyflow/react";
import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./lib/api";
import { useLogStream } from "./hooks/useSSE";
import { useWorkflowWebSocket, sendWebSocketMessage } from "./hooks/useWebSocket";
import { useAppStore } from "./store";
import type { ProjectResponse, WorkflowResponse } from "./types/api";
import { DataRouterModal } from "./components/DataRouterModal";
import { PairEditorModal } from "./components/PairEditorModal";
import { BlockPalette } from "./components/BlockPalette";
import { BottomPanel } from "./components/BottomPanel";
import { DataPreview } from "./components/DataPreview";
import { ProjectDialog } from "./components/ProjectDialog";
import { ProjectTree } from "./components/ProjectTree";
import { TabBar } from "./components/TabBar";
import { Toolbar } from "./components/Toolbar";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { WorkflowCanvas } from "./components/WorkflowCanvas";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "./components/ui/resizable";
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
  const setWorkflowName = useAppStore((state) => state.setWorkflowName);
  const setWorkflow = useAppStore((state) => state.setWorkflow);
  const addNode = useAppStore((state) => state.addNode);
  const updateNodeConfig = useAppStore((state) => state.updateNodeConfig);
  const updateNodeLayout = useAppStore((state) => state.updateNodeLayout);
  const connectNodes = useAppStore((state) => state.connectNodes);
  const removeNode = useAppStore((state) => state.removeNode);
  const removeEdge = useAppStore((state) => state.removeEdge);
  const addAnnotationNode = useAppStore((state) => state.addAnnotationNode);
  const addGroupNode = useAppStore((state) => state.addGroupNode);
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
  const interactivePrompt = useAppStore((state) => state.interactivePrompt);
  const setInteractivePrompt = useAppStore((state) => state.setInteractivePrompt);

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
  const toggleMinimap = useAppStore((state) => state.toggleMinimap);
  const setPanelSize = useAppStore((state) => state.setPanelSize);
  const setLastError = useAppStore((state) => state.setLastError);

  const blocks = useAppStore((state) => state.blocks);
  const blockSchemas = useAppStore((state) => state.blockSchemas);
  const paletteSearch = useAppStore((state) => state.paletteSearch);
  const setBlocks = useAppStore((state) => state.setBlocks);
  const setBlockSchema = useAppStore((state) => state.setBlockSchema);
  const setPaletteSearch = useAppStore((state) => state.setPaletteSearch);

  const previewCache = useAppStore((state) => state.previewCache);
  const previewLoading = useAppStore((state) => state.previewLoading);
  const cachePreview = useAppStore((state) => state.cachePreview);
  const setPreviewLoading = useAppStore((state) => state.setPreviewLoading);

  const tabs = useAppStore((state) => state.tabs);
  const activeTabId = useAppStore((state) => state.activeTabId);
  const openTab = useAppStore((state) => state.openTab);
  const switchTab = useAppStore((state) => state.switchTab);
  const closeTab = useAppStore((state) => state.closeTab);
  const syncActiveTab = useAppStore((state) => state.syncActiveTab);

  const [busy, setBusy] = useState(false);
  const [leftTab, setLeftTab] = useState<"blocks" | "project">("blocks");
  const bootedRef = useRef(false);

  const { connected: wsConnected } = useWorkflowWebSocket(Boolean(currentProject));
  const { connected: sseConnected } = useLogStream(workflowId, activeBottomTab === "logs" ? selectedNodeId : null);

  const selectedNode = useMemo(
    () => workflowNodes.find((node) => node.id === selectedNodeId) ?? null,
    [selectedNodeId, workflowNodes],
  );
  const selectedSchema = selectedNode ? blockSchemas[selectedNode.block_type] : undefined;
  const selectedNodeLabel =
    blocks.find((block) => block.type_name === selectedNode?.block_type)?.name ?? selectedNode?.block_type ?? "";

  const workflowPayload = useMemo<WorkflowResponse>(
    () => ({
      id: workflowId ?? "main",
      version: workflowVersion,
      description: workflowDescription,
      metadata: workflowMetadata,
      nodes: workflowNodes,
      edges: workflowEdges,
    }),
    [workflowDescription, workflowEdges, workflowId, workflowMetadata, workflowNodes, workflowVersion],
  );

  async function refreshProjects() {
    const projects = await api.listProjects();
    startTransition(() => setProjects(projects));
  }

  async function refreshBlocks() {
    const payload = await api.listBlocks();
    startTransition(() => setBlocks(payload.blocks));
    const schemas = await Promise.all(payload.blocks.map((block) => api.getBlockSchema(block.type_name)));
    startTransition(() => {
      schemas.forEach((schema) => setBlockSchema(schema));
    });
  }

  async function loadWorkflowForProject(project: ProjectResponse) {
    if (project.current_workflow_id) {
      const workflow = await api.getWorkflow(project.current_workflow_id);
      // #796: pass the workflow id as the displayName fallback so a YAML with
      // an empty `id:` still gets a non-blank tab label.
      openTab(workflow, project.current_workflow_id);
      return;
    }
    const workflow = emptyWorkflow("main");
    openTab(workflow, "main");
  }

  async function loadWorkflowById(wfId: string, displayName?: string) {
    try {
      const workflow = await api.getWorkflow(wfId);
      // #796: pass the caller-supplied displayName through to openTab so it can
      // fall back when workflow.id is empty (workflow YAML missing `id:`).
      openTab(workflow, displayName ?? wfId);
      resetExecution();
      setLastError(null);
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  async function openProject(projectIdOrPath: string) {
    setBusy(true);
    try {
      const project = await api.openProject(projectIdOrPath);
      // Bug 5: Clear current canvas state before loading new project.
      // Reset workflow and clear all tabs so old project state is gone.
      setWorkflow(null);
      resetExecution();
      // Force-clear all tabs from the store (useAppStore.setState is
      // available via the bound set, but the simplest approach is to
      // leverage the fact that openTab will create a fresh tab after
      // we clear the tabs array here).
      useAppStore.setState({ tabs: [], activeTabId: null });

      setCurrentProject(project);
      await refreshProjects();
      await loadWorkflowForProject(project);
      setLastError(null);
      closeProjectDialog();
    } catch (error) {
      setLastError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitProjectDialog() {
    setBusy(true);
    try {
      if (projectDialog.mode === "new") {
        const project = await api.createProject({
          name: projectDialog.name,
          description: projectDialog.description,
          path: projectDialog.path,
        });
        setCurrentProject(project);
        openTab(emptyWorkflow("main"));
        await refreshProjects();
      } else {
        await openProject(projectDialog.path);
        return;
      }
      closeProjectDialog();
      setLastError(null);
    } catch (error) {
      setLastError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject(projectId: string) {
    try {
      await api.deleteProject(projectId);
      // If the deleted project is the current one, close it
      if (currentProject?.id === projectId) {
        setCurrentProject(null);
        setWorkflow(null);
        resetExecution();
      }
      await refreshProjects();
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  async function saveWorkflow() {
    if (!currentProject) {
      return;
    }
    try {
      let saved: WorkflowResponse;
      try {
        saved = await api.updateWorkflow(workflowPayload.id, workflowPayload);
      } catch {
        saved = await api.createWorkflow(workflowPayload);
      }
      markWorkflowSaved();
      await refreshProjects();
      setCurrentProject({
        ...currentProject,
        current_workflow_id: saved.id,
        workflows: currentProject.workflows.includes(saved.id)
          ? currentProject.workflows
          : [...currentProject.workflows, saved.id],
      });
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  function newWorkflow() {
    const name = window.prompt("Workflow name:", "Untitled");
    if (name === null) return; // cancelled
    const id = name.trim() || "Untitled";
    const workflow = emptyWorkflow(id);
    openTab(workflow);
    resetExecution();
  }

  async function importWorkflow() {
    if (!currentProject) return;
    // Use an HTML file input to pick a YAML file, then upload via multipart
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".yaml,.yml";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const workflow = await api.importWorkflowFile(file);
        openTab(workflow);
        resetExecution();
        setLastError(null);

        // Update project's workflow list
        setCurrentProject({
          ...currentProject,
          current_workflow_id: workflow.id,
          workflows: currentProject.workflows.includes(workflow.id)
            ? currentProject.workflows
            : [...currentProject.workflows, workflow.id],
        });
      } catch (error) {
        setLastError((error as Error).message);
      }
    };
    input.click();
  }

  async function saveWorkflowAs() {
    if (!currentProject) return;

    // First, ensure the current workflow is saved to the project
    try {
      await saveWorkflow();
    } catch {
      // Ignore — saveWorkflow already sets lastError
    }

    // Open a native Save As dialog for .yaml files
    try {
      const defaultName = (workflowId ?? "Untitled") + ".yaml";
      const result = await api.openNativeSaveDialog({
        defaultFilename: defaultName,
        fileFilter: "YAML files (*.yaml)|*.yaml|All files (*.*)|*.*",
      });
      if (!result.paths || result.paths.length === 0) return; // cancelled
      let savePath = result.paths[0];

      // Ensure .yaml extension
      if (!savePath.endsWith(".yaml") && !savePath.endsWith(".yml")) {
        savePath += ".yaml";
      }

      // Export the workflow YAML to the chosen path
      await api.exportWorkflowToPath(workflowPayload.id, savePath);
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  async function loadPreview(dataRef: string) {
    try {
      setPreviewLoading(dataRef, true);
      const payload = await api.getDataPreview(dataRef);
      cachePreview(payload);
    } catch (error) {
      setPreviewLoading(dataRef, false);
      setLastError((error as Error).message);
    }
  }

  async function runWorkflow() {
    if (!currentProject) {
      return;
    }
    try {
      await saveWorkflow();
      const targetWorkflowId = workflowPayload.id;
      await api.executeWorkflow(targetWorkflowId);
      setLastError(null);
      // #793: do NOT auto-switch to the Logs tab. Engine events bump an unread
      // badge instead; the user navigates when they choose to.
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  async function pauseWorkflow() {
    if (!workflowId) {
      return;
    }
    await api.pauseWorkflow(workflowId);
  }

  async function resumeWorkflow() {
    if (!workflowId) {
      return;
    }
    await api.resumeWorkflow(workflowId);
  }

  async function cancelWorkflow() {
    if (!workflowId) {
      return;
    }
    await api.cancelWorkflow(workflowId);
  }

  async function startFromSelected() {
    if (!workflowId || !selectedNodeId) {
      return;
    }
    try {
      await saveWorkflow();
      await api.executeFrom(workflowId, selectedNodeId);
      setLastError(null);
      // #793: no auto tab-switch.
    } catch (error) {
      setLastError((error as Error).message);
    }
  }

  async function cancelSelectedBlock() {
    if (!workflowId || !selectedNodeId) {
      return;
    }
    await api.cancelBlock(workflowId, selectedNodeId);
  }

  const handleRunBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        await api.executeFrom(workflowId, blockId);
        setLastError(null);
        // #793: no auto tab-switch.
      } catch (error) {
        setLastError((error as Error).message);
      }
    },
    [saveWorkflow, setLastError, workflowId],
  );

  const handleRestartBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        await api.executeFrom(workflowId, blockId);
        setLastError(null);
        // #793: no auto tab-switch.
      } catch (error) {
        setLastError((error as Error).message);
      }
    },
    [saveWorkflow, setLastError, workflowId],
  );

  // #793: handleNodeSelect intentionally keeps the "config" switch because
  // selecting a node IS an explicit user request to see that node's config.
  const handleNodeSelect = useCallback(
    (nodeId: string | null) => {
      setSelectedNodeId(nodeId);
      if (nodeId) {
        setActiveBottomTab("config");
      }
    },
    [setSelectedNodeId, setActiveBottomTab],
  );

  // Clicking an error badge on a block selects that node and opens the
  // Logs tab — the same tab that now hosts the (filterable) error rows
  // since the dedicated Problems tab was removed.
  const handleErrorClick = useCallback(
    (blockId: string) => {
      setSelectedNodeId(blockId);
      setActiveBottomTab("logs");
    },
    [setSelectedNodeId, setActiveBottomTab],
  );

  // Boot: load projects and blocks
  useEffect(() => {
    if (bootedRef.current) {
      return;
    }
    bootedRef.current = true;
    void (async () => {
      setBusy(true);
      try {
        await Promise.all([refreshProjects(), refreshBlocks()]);
      } catch (error) {
        setLastError((error as Error).message);
      } finally {
        setBusy(false);
      }
    })();
  }, []);

  // Auto-save on dirty
  useEffect(() => {
    if (!currentProject || !workflowDirty) {
      return undefined;
    }
    const timeout = window.setTimeout(() => {
      void saveWorkflow();
    }, 800);
    return () => window.clearTimeout(timeout);
  }, [currentProject, workflowDirty, workflowPayload]);

  // Sync active tab snapshot when workflow state changes
  useEffect(() => {
    if (activeTabId) {
      syncActiveTab();
    }
  }, [workflowNodes, workflowEdges, workflowDirty, workflowDescription, selectedNodeId]);

  // Keyboard shortcuts
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT";
      const ctrl = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();

      // Escape always works
      if (event.key === "Escape") {
        event.preventDefault();
        setSelectedNodeId(null);
        return;
      }

      // Ctrl+S always works
      if (ctrl && key === "s" && !event.shiftKey) {
        event.preventDefault();
        void saveWorkflow();
        return;
      }

      // Ctrl+Shift+S: Save As
      if (ctrl && key === "s" && event.shiftKey) {
        event.preventDefault();
        void saveWorkflowAs();
        return;
      }

      // Skip other shortcuts when in input fields
      if (isInput) return;

      if (ctrl && key === "z") {
        event.preventDefault();
        undoWorkflow();
      } else if (ctrl && key === "y") {
        event.preventDefault();
        redoWorkflow();
      } else if (ctrl && key === "enter") {
        event.preventDefault();
        void runWorkflow();
      } else if (ctrl && key === ".") {
        event.preventDefault();
        void cancelWorkflow();
      } else if (ctrl && key === "b") {
        event.preventDefault();
        togglePalette();
      } else if (ctrl && key === "d") {
        event.preventDefault();
        togglePreview();
      } else if (ctrl && key === "j") {
        event.preventDefault();
        toggleBottomPanel();
      } else if (ctrl && key === "m") {
        event.preventDefault();
        toggleMinimap();
      } else if (ctrl && key === "o") {
        event.preventDefault();
        openProjectDialog("open");
      } else if (ctrl && key === "a") {
        event.preventDefault();
        // Select all handled by ReactFlow internally
      } else if ((event.key === "Delete" || event.key === "Backspace") && selectedNodeId) {
        removeNode(selectedNodeId);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [
    cancelWorkflow,
    openProjectDialog,
    redoWorkflow,
    removeNode,
    runWorkflow,
    saveWorkflow,
    saveWorkflowAs,
    selectedNodeId,
    setSelectedNodeId,
    toggleBottomPanel,
    toggleMinimap,
    togglePalette,
    togglePreview,
    undoWorkflow,
  ]);

  // ADR-034 Phase 1.3: the legacy onSendChat / AIChat plumbing was removed.
  // The AI Chat bottom tab now hosts <TerminalTabs/>, which manages its own
  // PTY-backed sessions through `terminalTabsSlice`.

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
            recentProjects={recentProjects}
            onNewProject={() => openProjectDialog("new", { path: projectDialog.path })}
            onOpenProject={() => openProjectDialog("open")}
            onOpenRecent={(project) => void openProject(project.id)}
            onCloseProject={() => {
              setCurrentProject(null);
              setWorkflow(emptyWorkflow());
              resetExecution();
            }}
            onNewWorkflow={() => newWorkflow()}
            onSave={() => void saveWorkflow()}
            onSaveAs={() => void saveWorkflowAs()}
            onImport={() => void importWorkflow()}
            onRun={() => void runWorkflow()}
            onPause={() => void pauseWorkflow()}
            onResume={() => void resumeWorkflow()}
            onStop={() => void cancelWorkflow()}
            onReset={() => resetExecution()}
            onDelete={() => {
              if (selectedNodeId) removeNode(selectedNodeId);
            }}
            onReloadBlocks={() => void refreshBlocks()}
            onStartFromSelected={() => void startFromSelected()}
            onAddAnnotation={() => addAnnotationNode({ x: 150 + Math.random() * 200, y: 150 + Math.random() * 200 })}
            onAddGroup={() => addGroupNode({ x: 150 + Math.random() * 200, y: 150 + Math.random() * 200 })}
            isRunning={isRunning}
          />

          {lastError ? (
            <div className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700">{lastError}</div>
          ) : null}

          {currentProject ? (
            <ResizablePanelGroup
              orientation="horizontal"
              className="min-h-0 flex-1"
              onLayoutChanged={(layout) => {
                const sizes = Object.values(layout);
                if (sizes[0] != null && sizes[0] >= 4) setPanelSize("palette", sizes[0]);
                if (sizes[2] != null && sizes[2] >= 4) setPanelSize("preview", sizes[2]);
              }}
            >
              {/* Left Sidebar — tab switcher + content */}
              <ResizablePanel defaultSize="15%" minSize="4%" maxSize="28%" collapsible collapsedSize="0%">
                <div className="flex h-full flex-col overflow-hidden">
                  {/* Tab switcher */}
                  <div className="flex shrink-0 border-b border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))]">
                    <button
                      className={`flex-1 px-3 py-2 text-xs font-medium transition ${leftTab === "blocks" ? "border-b-2 border-ember text-ink" : "text-stone-400 hover:text-stone-600"}`}
                      onClick={() => setLeftTab("blocks")}
                      type="button"
                    >
                      Blocks
                    </button>
                    <button
                      className={`flex-1 px-3 py-2 text-xs font-medium transition ${leftTab === "project" ? "border-b-2 border-ember text-ink" : "text-stone-400 hover:text-stone-600"}`}
                      onClick={() => setLeftTab("project")}
                      type="button"
                    >
                      Project
                    </button>
                  </div>
                  {/* Tab content */}
                  <div className="min-h-0 flex-1">
                    {leftTab === "blocks" ? (
                      <BlockPalette
                        blocks={blocks}
                        collapsed={false}
                        onAddBlock={(block) => {
                          const defaultParams: Record<string, unknown> = {};
                          if (block.direction) {
                            defaultParams.direction = block.direction;
                          } else if (block.type_name === "io_block") {
                            defaultParams.direction = block.name === "Load Block" ? "input" : "output";
                          }
                          // Bug 7: Set default output_dir for AppBlocks when a project is open
                          if (block.base_category === "app" && currentProject) {
                            defaultParams.output_dir = `${currentProject.path}/data/exchange/outputs`;
                          }
                          addNode(block, { x: 160, y: 160 }, Object.keys(defaultParams).length > 0 ? defaultParams : undefined);
                        }}
                        onReload={() => void refreshBlocks()}
                        onSearch={setPaletteSearch}
                        search={paletteSearch}
                      />
                    ) : currentProject ? (
                      <ProjectTree
                        projectId={currentProject.id}
                        projectPath={currentProject.path}
                        onLoadWorkflow={(workflowId, displayName) => void loadWorkflowById(workflowId, displayName)}
                        onReloadBlocks={() => void refreshBlocks()}
                      />
                    ) : (
                      <div className="p-4 text-xs text-stone-400">No project open</div>
                    )}
                  </div>
                </div>
              </ResizablePanel>
              <ResizableHandle withHandle />

              {/* Center: Tab Bar + Canvas + Bottom Panel vertical split */}
              <ResizablePanel defaultSize="63%">
                <div className="flex h-full flex-col">
                <TabBar
                  tabs={tabs}
                  activeTabId={activeTabId}
                  onSwitchTab={switchTab}
                  onCloseTab={closeTab}
                  onNewTab={() => newWorkflow()}
                />
                <ResizablePanelGroup
                  orientation="vertical"
                  className="min-h-0 flex-1"
                  onLayoutChanged={(layout) => {
                    const sizes = Object.values(layout);
                    if (sizes[1] != null && sizes[1] >= 10) setPanelSize("bottom", sizes[1]);
                  }}
                >
                  <ResizablePanel defaultSize="70%" minSize="20%">
                    <WorkflowCanvas
                      blockStates={blockStates}
                      blockErrors={blockErrors}
                      blockErrorSummaries={blockErrorSummaries}
                      blocks={blocks.filter((block) => {
                        const value = `${block.name} ${block.description} ${block.subcategory || block.base_category}`.toLowerCase();
                        return value.includes(paletteSearch.toLowerCase());
                      })}
                      edges={workflowEdges}
                      minimapVisible={minimapVisible}
                      nodes={workflowNodes}
                      onAddNode={addNode}
                      onConnect={async (edge) => {
                        try {
                          const sourceNode = workflowNodes.find((node) => node.id === edge.source.split(":")[0]);
                          const targetNode = workflowNodes.find((node) => node.id === edge.target.split(":")[0]);
                          if (!sourceNode || !targetNode) {
                            return;
                          }
                          const sourcePort = edge.source.split(":")[1];
                          const targetPort = edge.target.split(":")[1];
                          const validation = await api.validateConnection({
                            source_block: sourceNode.block_type,
                            source_port: sourcePort,
                            target_block: targetNode.block_type,
                            target_port: targetPort,
                          });
                          if (!validation.compatible) {
                            setLastError(validation.reason);
                            return;
                          }
                          connectNodes(edge);
                          setLastError(null);
                        } catch (error) {
                          setLastError((error as Error).message);
                        }
                      }}
                      onDeleteEdge={removeEdge}
                      onDeleteNode={removeNode}
                      onErrorClick={handleErrorClick}
                      onRunBlock={handleRunBlock}
                      onRestartBlock={handleRestartBlock}
                      onSelectNode={handleNodeSelect}
                      onUpdateNodeConfig={updateNodeConfig}
                      onUpdateNodePosition={updateNodeLayout}
                      schemas={blockSchemas}
                      selectedNodeId={selectedNodeId}
                    />
                  </ResizablePanel>
                  <ResizableHandle withHandle />
                  <ResizablePanel defaultSize="30%" minSize="5%" collapsible collapsedSize="3%">
                    <BottomPanel
                      activeTab={activeBottomTab}
                      logEntries={logEntries}
                      onTabChange={setActiveBottomTab}
                      onUpdateConfig={(patch) => {
                        if (selectedNodeId) {
                          updateNodeConfig(selectedNodeId, patch);
                        }
                      }}
                      selectedNode={selectedNode}
                      selectedSchema={selectedSchema}
                      unreadLogsCount={unreadLogsCount}
                    />
                  </ResizablePanel>
                </ResizablePanelGroup>
                </div>
              </ResizablePanel>
              <ResizableHandle withHandle />

              {/* Data Preview — full height right column */}
              <ResizablePanel defaultSize="22%" minSize="15%" maxSize="42%" collapsible collapsedSize="0%">
                <DataPreview
                  blockOutputs={blockOutputs}
                  onCancelSelected={() => void cancelSelectedBlock()}
                  onLoadPreview={loadPreview}
                  onStartFromHere={() => void startFromSelected()}
                  previewCache={previewCache}
                  previewLoading={previewLoading}
                  selectedNodeId={selectedNodeId}
                  selectedNodeLabel={selectedNodeLabel}
                />
              </ResizablePanel>
            </ResizablePanelGroup>
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

          {/* #591/#594: Interactive block modals */}
          {interactivePrompt?.blockType === "DataRouter" && (
            <DataRouterModal
              blockId={interactivePrompt.blockId}
              inputPorts={(interactivePrompt.data.input_ports as string[]) ?? []}
              outputPorts={(interactivePrompt.data.output_ports as string[]) ?? []}
              itemsPerPort={
                (interactivePrompt.data.items_per_port as Record<
                  string,
                  Array<{ index: number; port: string; ref: string; name: string; type: string }>
                >) ?? {}
              }
              onConfirm={(assignments) => {
                sendWebSocketMessage({
                  type: "interactive_complete",
                  block_id: interactivePrompt.blockId,
                  data: { assignments },
                });
                setInteractivePrompt(null);
              }}
              onCancel={() => {
                sendWebSocketMessage({
                  type: "cancel_block",
                  block_id: interactivePrompt.blockId,
                  workflow_id: workflowId,
                });
                setInteractivePrompt(null);
              }}
            />
          )}
          {interactivePrompt?.blockType === "PairEditor" && (
            <PairEditorModal
              blockId={interactivePrompt.blockId}
              ports={(interactivePrompt.data.ports as string[]) ?? []}
              itemsPerPort={
                (interactivePrompt.data.items_per_port as Record<
                  string,
                  Array<{ index: number; name: string; type: string }>
                >) ?? {}
              }
              collectionLength={(interactivePrompt.data.collection_length as number) ?? 0}
              onConfirm={(reorder) => {
                sendWebSocketMessage({
                  type: "interactive_complete",
                  block_id: interactivePrompt.blockId,
                  data: { reorder },
                });
                setInteractivePrompt(null);
              }}
              onCancel={() => {
                sendWebSocketMessage({
                  type: "cancel_block",
                  block_id: interactivePrompt.blockId,
                  workflow_id: workflowId,
                });
                setInteractivePrompt(null);
              }}
            />
          )}

          {busy ? (
            <div className="fixed bottom-4 right-4 rounded-full bg-ink px-4 py-2 text-sm text-white">Working…</div>
          ) : null}
        </div>
      </TooltipProvider>
    </ReactFlowProvider>
  );
}
