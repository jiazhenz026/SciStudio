// Extracted from App.tsx as part of the #1422 god-file split.
//
// ProjectWorkspace — the three-column ResizablePanelGroup tree shown when a
// project is open: BlockPalette/ProjectTree on the left, TabBar +
// (CodeEditor | WorkflowCanvas) + BottomPanel in the middle, DataPreview on
// the right. This is the bulk of App.tsx's JSX before the refactor; pulling
// it into a presentation component lets App.tsx focus on lifecycle and
// state wiring.

import type { PanelImperativeHandle } from "react-resizable-panels";
import type { RefObject } from "react";

import type { useAppStore } from "../store";
import type { AnyTab, FileTab } from "../store/types";
import type {
  BlockSchemaResponse,
  BlockSummary,
  ProjectResponse,
  WorkflowEdge,
  WorkflowNode,
} from "../types/api";

import { BlockPalette } from "../components/BlockPalette";
import { BottomPanel } from "../components/BottomPanel";
import { CodeEditor } from "../components/CodeEditor";
import { DataPreview } from "../components/DataPreview";
import { ProjectTree } from "../components/ProjectTree";
import { TabBar } from "../components/TabBar";
import { WorkflowCanvas } from "../components/WorkflowCanvas";
import { resolveVariadicPorts } from "../components/WorkflowCanvas.parts/flowNodeBuilder";
import { buildScopedBlockOutputs } from "../components/WorkflowCanvas.parts/subworkflowRunView";
import { SUBWORKFLOW_BLOCK_TYPES } from "../components/WorkflowCanvas.parts/useFlowNodes";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "../components/ui/resizable";
import { computeEffectivePorts } from "../utils/computeEffectivePorts";

type BottomTabValue = ReturnType<typeof useAppStore.getState>["activeBottomTab"];

/** ADR-050 §3 — focus mode + tidy layout wiring passed to the canvas. */
export interface CanvasReadabilityWiring {
  focusMode: { enabled: boolean; selectedIds: string[]; depth: number };
  /** ADR-050 FR-013 — warning status → select node + open Config detail. */
  onWarningClick: (blockId: string) => void;
  onEnterFocusMode: (selectedIds: string[]) => void;
  onExitFocusMode: () => void;
  onTidyLayout: (positions: Record<string, { x: number; y: number }>) => void;
}

export interface ProjectWorkspaceProps {
  // Project / workflow context
  currentProject: ProjectResponse;
  // Left panel
  leftTab: "blocks" | "project";
  onLeftTabChange: (tab: "blocks" | "project") => void;
  blocks: BlockSummary[];
  paletteSearch: string;
  setPaletteSearch: (search: string) => void;
  onAddBlockFromPalette: (block: BlockSummary) => void;
  onReloadBlocks: () => void;
  onLoadWorkflowById: (workflowId: string, displayName?: string) => void;
  // Tabs
  tabs: AnyTab[];
  activeTabId: string | null;
  activeFileTab: FileTab | null;
  switchTab: (id: string) => void;
  closeTab: (id: string) => void;
  onNewWorkflowTab: () => void;
  // File-tab editor
  updateFileTabContent: (id: string, content: string) => void;
  saveFileTab: (id: string) => Promise<void>;
  // Workflow canvas
  blockStates: ReturnType<typeof useAppStore.getState>["blockStates"];
  blockOutputs: ReturnType<typeof useAppStore.getState>["blockOutputs"];
  blockErrors: ReturnType<typeof useAppStore.getState>["blockErrors"];
  blockErrorSummaries: ReturnType<typeof useAppStore.getState>["blockErrorSummaries"];
  blockSchemas: Record<string, BlockSchemaResponse>;
  workflowNodes: WorkflowNode[];
  workflowEdges: WorkflowEdge[];
  selectedNodeId: string | null;
  minimapVisible: boolean;
  onCanvasAddNode: (
    block: BlockSummary,
    position: { x: number; y: number },
    defaultParams?: Record<string, unknown>,
  ) => void;
  onCanvasConnect: (edge: WorkflowEdge) => Promise<void>;
  onCanvasDeleteEdge: (edge: WorkflowEdge) => void;
  onCanvasDeleteNode: (nodeId: string) => void;
  onErrorClick: (blockId: string) => void;
  onCanvasPaneClick: () => void;
  onRunBlock: (blockId: string) => Promise<void> | void;
  onRestartBlock: (blockId: string) => Promise<void> | void;
  onSelectNode: (nodeId: string | null) => void;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
  onUpdateNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
  onResizeNode: (nodeId: string, size: { width: number; height: number }) => void;
  /**
   * ADR-044 §3 — open a subworkflow node's referenced file
   * (`config.ref.path`) in a canvas tab on double-click.
   */
  onOpenSubworkflow: (refPath: string, runPrefix?: string) => void;
  /**
   * ADR-044 §10 — broken-ref "locate file…" affordance for a
   * `subworkflow_broken` placeholder node.
   */
  onLocateSubworkflow: (nodeId: string) => void;
  /** ADR-050 §3 — focus-mode + tidy-layout wiring, grouped into one prop. */
  readability: CanvasReadabilityWiring;
  // Bottom panel
  bottomPanelRef: RefObject<PanelImperativeHandle | null>;
  bottomPanelPinned: boolean;
  toggleBottomPanelPinned: () => void;
  activeBottomTab: BottomTabValue;
  onBottomTabChange: (tab: BottomTabValue) => void;
  logEntries: ReturnType<typeof useAppStore.getState>["logEntries"];
  unreadLogsCount: number;
  selectedNode: WorkflowNode | null;
  selectedSchema?: BlockSchemaResponse;
  // Data preview
  selectedNodeLabel: string;
  // Layout persistence
  setPanelSize: (key: "palette" | "preview" | "bottom", size: number) => void;
}

function PaletteOrProjectPane(props: ProjectWorkspaceProps) {
  const {
    leftTab,
    onLeftTabChange,
    blocks,
    onAddBlockFromPalette,
    onReloadBlocks,
    setPaletteSearch,
    paletteSearch,
    currentProject,
    onLoadWorkflowById,
  } = props;
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 border-b border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))]">
        <button
          className={`flex-1 px-3 py-2 text-xs font-medium transition ${leftTab === "blocks" ? "border-b-2 border-ember text-ink" : "text-stone-400 hover:text-stone-600"}`}
          onClick={() => onLeftTabChange("blocks")}
          type="button"
        >
          Blocks
        </button>
        <button
          className={`flex-1 px-3 py-2 text-xs font-medium transition ${leftTab === "project" ? "border-b-2 border-ember text-ink" : "text-stone-400 hover:text-stone-600"}`}
          onClick={() => onLeftTabChange("project")}
          type="button"
        >
          Project
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {leftTab === "blocks" ? (
          <BlockPalette
            blocks={blocks}
            collapsed={false}
            onAddBlock={onAddBlockFromPalette}
            onReload={onReloadBlocks}
            onSearch={setPaletteSearch}
            search={paletteSearch}
          />
        ) : (
          <ProjectTree
            projectId={currentProject.id}
            projectPath={currentProject.path}
            onLoadWorkflow={(workflowId, displayName) =>
              onLoadWorkflowById(workflowId, displayName)
            }
            onReloadBlocks={onReloadBlocks}
          />
        )}
      </div>
    </div>
  );
}

/**
 * ADR-044 — derive the active canvas's run-scope prefix (from the active tab's
 * `runPrefix`, set when it was opened by expanding a subworkflow node) and the
 * block-outputs map re-keyed for that canvas: child nodes aliased to their
 * flattened run outputs, and each subworkflow node mapped from its exposed
 * outputs to inner block outputs. Both the canvas (status) and the preview
 * panels read from this so the collapsed/expanded views show live data.
 */
function deriveRunScope(props: ProjectWorkspaceProps): {
  runScopePrefix: string;
  scopedBlockOutputs: Record<string, Record<string, unknown>>;
} {
  const activeTab = props.tabs.find((tab) => tab.id === props.activeTabId);
  const runScopePrefix = activeTab?.kind === "workflow" ? (activeTab.runPrefix ?? "") : "";
  const scopedBlockOutputs = buildScopedBlockOutputs(
    props.workflowNodes,
    props.blockOutputs,
    runScopePrefix,
  );
  return { runScopePrefix, scopedBlockOutputs };
}

function CanvasOrEditor(props: ProjectWorkspaceProps) {
  const {
    activeFileTab,
    updateFileTabContent,
    saveFileTab,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    blocks,
    paletteSearch,
    workflowEdges,
    workflowNodes,
    selectedNodeId,
    minimapVisible,
    onCanvasAddNode,
    onCanvasConnect,
    onCanvasDeleteEdge,
    onCanvasDeleteNode,
    onErrorClick,
    onCanvasPaneClick,
    onRunBlock,
    onRestartBlock,
    onSelectNode,
    onUpdateNodeConfig,
    onUpdateNodePosition,
    onResizeNode,
    onOpenSubworkflow,
    onLocateSubworkflow,
    blockSchemas,
    readability,
  } = props;

  const { runScopePrefix, scopedBlockOutputs } = deriveRunScope(props);

  if (activeFileTab) {
    return (
      <CodeEditor
        tab={activeFileTab}
        onContentChange={(content) => {
          try {
            updateFileTabContent(activeFileTab.id, content);
          } catch (error) {
            // Skeleton stub throws; soft-warn so the UI still works in dev
            // mode pre-I36a-merge.
            console.warn(`updateFileTabContent(${activeFileTab.id}) failed:`, error);
          }
        }}
        onSave={() => {
          if (activeFileTab.readOnly) return;
          void saveFileTab(activeFileTab.id).catch((error) => {
            console.warn(`saveFileTab(${activeFileTab.id}) failed:`, error);
          });
        }}
      />
    );
  }

  return (
    <WorkflowCanvas
      blockStates={blockStates}
      blockErrors={blockErrors}
      blockErrorSummaries={blockErrorSummaries}
      blockOutputs={scopedBlockOutputs}
      runScopePrefix={runScopePrefix}
      blocks={blocks.filter((block) => {
        const value =
          `${block.name} ${block.description} ${block.subcategory || block.base_category}`.toLowerCase();
        return value.includes(paletteSearch.toLowerCase());
      })}
      edges={workflowEdges}
      minimapVisible={minimapVisible}
      nodes={workflowNodes}
      onAddNode={onCanvasAddNode}
      onConnect={onCanvasConnect}
      onDeleteEdge={onCanvasDeleteEdge}
      onDeleteNode={onCanvasDeleteNode}
      onErrorClick={onErrorClick}
      onWarningClick={readability.onWarningClick}
      onPaneClick={onCanvasPaneClick}
      onRunBlock={onRunBlock}
      onRestartBlock={onRestartBlock}
      onSelectNode={onSelectNode}
      onUpdateNodeConfig={onUpdateNodeConfig}
      onUpdateNodePosition={onUpdateNodePosition}
      onResizeNode={onResizeNode}
      onOpenSubworkflow={onOpenSubworkflow}
      onLocateSubworkflow={onLocateSubworkflow}
      schemas={blockSchemas}
      selectedNodeId={selectedNodeId}
      focusMode={readability.focusMode}
      onEnterFocusMode={readability.onEnterFocusMode}
      onExitFocusMode={readability.onExitFocusMode}
      onTidyLayout={readability.onTidyLayout}
    />
  );
}

export function ProjectWorkspace(props: ProjectWorkspaceProps) {
  const {
    tabs,
    activeTabId,
    switchTab,
    closeTab,
    onNewWorkflowTab,
    bottomPanelRef,
    bottomPanelPinned,
    toggleBottomPanelPinned,
    activeBottomTab,
    onBottomTabChange,
    logEntries,
    unreadLogsCount,
    selectedNode,
    selectedSchema,
    selectedNodeId,
    onUpdateNodeConfig,
    setPanelSize,
    workflowEdges,
    selectedNodeLabel,
  } = props;

  // ADR-044 — preview panels read the same run-scoped, exposed-mapped outputs as
  // the canvas, so selecting a subworkflow node (or a node in an expanded child
  // canvas) shows its live data.
  const { scopedBlockOutputs } = deriveRunScope(props);

  // ADR-044 — when a subworkflow node is selected, surface its exposed-port
  // surface (with owning-block provenance) so the preview pane can show which
  // inner block each opaque "<block>.<port>" port belongs to.
  const subworkflowPorts =
    selectedNode &&
    SUBWORKFLOW_BLOCK_TYPES.has(selectedNode.block_type) &&
    selectedNode.resolved_ports
      ? {
          inputs: selectedNode.resolved_ports.inputs,
          outputs: selectedNode.resolved_ports.outputs,
          typeHierarchy: Object.values(props.blockSchemas).find(
            (schema) => (schema.type_hierarchy?.length ?? 0) > 0,
          )?.type_hierarchy,
        }
      : undefined;

  return (
    <ResizablePanelGroup
      orientation="horizontal"
      className="min-h-0 flex-1"
      onLayoutChanged={(layout) => {
        const sizes = Object.values(layout);
        const palette = sizes[0];
        const preview = sizes[2];
        if (palette !== null && palette !== undefined && palette >= 4) {
          setPanelSize("palette", palette);
        }
        if (preview !== null && preview !== undefined && preview >= 4) {
          setPanelSize("preview", preview);
        }
      }}
    >
      {/* Left Sidebar — tab switcher + content */}
      <ResizablePanel defaultSize="15%" minSize="4%" maxSize="28%" collapsible collapsedSize="0%">
        <PaletteOrProjectPane {...props} />
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
            onNewTab={onNewWorkflowTab}
          />
          <ResizablePanelGroup
            orientation="vertical"
            className="min-h-0 flex-1"
            onLayoutChanged={(layout) => {
              const sizes = Object.values(layout);
              const bottom = sizes[1];
              if (bottom !== null && bottom !== undefined && bottom >= 10) {
                setPanelSize("bottom", bottom);
              }
            }}
          >
            <ResizablePanel defaultSize="70%" minSize="20%">
              <CanvasOrEditor {...props} />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel
              panelRef={bottomPanelRef}
              // collapsedSize is in % of the canvas-column height. 8% on a
              // typical 800–1000px column ≈ 64–80px, which accommodates the
              // ~60px tab strip without clipping it. The previous 3%
              // (~24–30px) cut off the bottom half of the tab buttons.
              collapsedSize="8%"
              collapsible
              // 45% gives Git / Lineage / Logs tabs enough vertical room
              // for their list + detail content out-of-the-box. 30% (prior
              // default) made the Git history list unreadable on a 1080p
              // canvas column.
              defaultSize="45%"
              minSize="10%"
            >
              <BottomPanel
                activeTab={activeBottomTab}
                blockOutputs={scopedBlockOutputs}
                edges={workflowEdges}
                logEntries={logEntries}
                onTabChange={onBottomTabChange}
                onTogglePin={toggleBottomPanelPinned}
                onUpdateConfig={(patch) => {
                  if (selectedNodeId) {
                    onUpdateNodeConfig(selectedNodeId, patch);
                  }
                }}
                pinned={bottomPanelPinned}
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
          blockOutputs={scopedBlockOutputs}
          subworkflowPorts={subworkflowPorts}
          selectedNodeId={selectedNodeId}
          selectedNodeLabel={selectedNodeLabel}
          // #1326 port-info panel: resolve effective per-instance ports for
          // the selected node.
          //
          // Hotfix 2026-05-23: ``node.config`` is a two-tier envelope where
          // user-editable params live under ``node.config.params`` (see
          // ``mergeNodeConfig``). The canvas-side BlockNode reads
          // ``paramsOf(node) = node.config.params``; we mirror that here so
          // both ``resolveVariadicPorts`` (variadic ports stored at
          // ``params.{input,output}_ports``) AND ``computeEffectivePorts``
          // (dynamic-port driving key at ``params.core_type``) see the
          // same config the canvas sees. Reading ``node.config`` directly
          // was a pre-existing bug that hid newly-added variadic ports
          // from the panel and froze dynamic-port types at their
          // schema-static fallback ``DataObject``.
          selectedInputPorts={
            selectedNode && selectedSchema
              ? computeEffectivePorts(
                  selectedSchema.dynamic_ports ?? null,
                  selectedSchema.dynamic_ports?.source_config_key
                    ? (((selectedNode.config.params as Record<string, unknown> | undefined) ?? {})[
                        selectedSchema.dynamic_ports.source_config_key
                      ] as string | undefined)
                    : undefined,
                  resolveVariadicPorts(
                    selectedSchema.input_ports,
                    (selectedNode.config.params as Record<string, unknown> | undefined) ?? {},
                    "input",
                    selectedSchema,
                  ),
                  "input",
                )
              : undefined
          }
          selectedOutputPorts={
            selectedNode && selectedSchema
              ? computeEffectivePorts(
                  selectedSchema.dynamic_ports ?? null,
                  selectedSchema.dynamic_ports?.source_config_key
                    ? (((selectedNode.config.params as Record<string, unknown> | undefined) ?? {})[
                        selectedSchema.dynamic_ports.source_config_key
                      ] as string | undefined)
                    : undefined,
                  resolveVariadicPorts(
                    selectedSchema.output_ports,
                    (selectedNode.config.params as Record<string, unknown> | undefined) ?? {},
                    "output",
                    selectedSchema,
                  ),
                  "output",
                )
              : undefined
          }
          selectedSchema={selectedSchema}
        />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
