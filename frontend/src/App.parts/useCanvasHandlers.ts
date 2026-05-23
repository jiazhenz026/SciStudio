// Extracted from App.tsx as part of the #1422 god-file split.
//
// useCanvasHandlers — the callbacks the workflow canvas + toolbar dispatch
// when the user clicks "Add Block" in the palette, drags an edge between
// two ports, asks for the workflow YAML ("View source"), or hits the
// global Save button. These are all bound handlers that exist purely to
// keep App.tsx focused on the render tree and lifecycle.

import { useCallback } from "react";

import { api } from "../lib/api";
import type { BlockSummary, ProjectResponse, WorkflowEdge, WorkflowNode } from "../types/api";
import type { FileTab } from "../store/types";

export interface CanvasHandlersDeps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  workflowNodes: WorkflowNode[];
  workflowEdges: WorkflowEdge[];
  activeFileTab: FileTab | null;
  addNode: (
    block: BlockSummary,
    position: { x: number; y: number },
    defaultParams?: Record<string, unknown>,
  ) => void;
  connectNodes: (edge: WorkflowEdge) => void;
  openFileTab: (path: string, options?: { readOnly?: boolean }) => void;
  saveFileTab: (tabId: string) => Promise<void>;
  saveWorkflow: () => Promise<void>;
  setLastError: (message: string | null) => void;
}

// Returns true if adding ``sourceNodeId -> targetNodeId`` to the existing
// edge set would create a cycle (including the self-loop case
// ``sourceNodeId === targetNodeId``). Walks outgoing edges from the
// proposed target; a path back to source means the new edge closes a cycle.
function wouldCreateCycle(
  sourceNodeId: string,
  targetNodeId: string,
  existingEdges: WorkflowEdge[],
): boolean {
  if (sourceNodeId === targetNodeId) return true;
  const adjacency = new Map<string, string[]>();
  for (const edge of existingEdges) {
    const [src] = edge.source.split(":");
    const [tgt] = edge.target.split(":");
    if (!src || !tgt) continue;
    const list = adjacency.get(src);
    if (list) list.push(tgt);
    else adjacency.set(src, [tgt]);
  }
  const stack: string[] = [targetNodeId];
  const visited = new Set<string>();
  while (stack.length > 0) {
    const node = stack.pop() as string;
    if (node === sourceNodeId) return true;
    if (visited.has(node)) continue;
    visited.add(node);
    const next = adjacency.get(node);
    if (next) stack.push(...next);
  }
  return false;
}

export interface CanvasHandlers {
  handleAddBlockFromPalette: (block: BlockSummary) => void;
  handleCanvasConnect: (edge: WorkflowEdge) => Promise<void>;
  handleViewSource: () => Promise<void>;
  handleSave: () => void;
}

export function useCanvasHandlers(deps: CanvasHandlersDeps): CanvasHandlers {
  const {
    currentProject,
    workflowId,
    workflowNodes,
    workflowEdges,
    activeFileTab,
    addNode,
    connectNodes,
    openFileTab,
    saveFileTab,
    saveWorkflow,
    setLastError,
  } = deps;

  const handleAddBlockFromPalette = useCallback(
    (block: BlockSummary) => {
      const defaultParams: Record<string, unknown> = {};
      if (block.direction) {
        defaultParams.direction = block.direction;
      } else if (block.type_name === "io_block") {
        defaultParams.direction = block.name === "Load Block" ? "input" : "output";
      }
      // Bug 7: default output_dir for AppBlocks when a project is open.
      if (block.base_category === "app" && currentProject) {
        defaultParams.output_dir = `${currentProject.path}/data/exchange/outputs`;
      }
      addNode(
        block,
        { x: 160, y: 160 },
        Object.keys(defaultParams).length > 0 ? defaultParams : undefined,
      );
    },
    [addNode, currentProject],
  );

  const handleCanvasConnect = useCallback(
    async (edge: WorkflowEdge) => {
      try {
        const sourceNode = workflowNodes.find((node) => node.id === edge.source.split(":")[0]);
        const targetNode = workflowNodes.find((node) => node.id === edge.target.split(":")[0]);
        if (!sourceNode || !targetNode) return;
        const sourcePort = edge.source.split(":")[1];
        const targetPort = edge.target.split(":")[1];
        // Hotfix 2026-05-23 — pre-runtime cycle check. The frontend used
        // to surface "Workflow contains a cycle" as soon as a self-loop or
        // back-edge was drawn, but the backend ``validate_connection``
        // endpoint only checks per-edge type compat. Re-enforce cycle
        // rejection here so the UI never accepts a connection that would
        // make ``validate_workflow`` fail at save / run time.
        if (wouldCreateCycle(sourceNode.id, targetNode.id, workflowEdges)) {
          setLastError(
            sourceNode.id === targetNode.id
              ? "Cannot connect a block to itself."
              : "This connection would create a cycle in the workflow.",
          );
          return;
        }
        // #889: pass node configs so the backend resolves effective
        // ports (LoadData core_type, variadic block-declared ports)
        // rather than validating against the static class-level
        // spec.
        const validation = await api.validateConnection({
          source_block: sourceNode.block_type,
          source_port: sourcePort,
          target_block: targetNode.block_type,
          target_port: targetPort,
          source_node_config: sourceNode.config,
          target_node_config: targetNode.config,
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
    },
    [connectNodes, setLastError, workflowNodes, workflowEdges],
  );

  const handleViewSource = useCallback(async () => {
    if (!currentProject || !workflowId) return;
    // #878: ensure the workflow exists on disk before opening its YAML.
    try {
      await saveWorkflow();
    } catch (error) {
      console.warn("View source: saveWorkflow failed", error);
      return;
    }
    openFileTab(`workflows/${workflowId}.yaml`, { readOnly: true });
  }, [currentProject, openFileTab, saveWorkflow, workflowId]);

  const handleSave = useCallback(() => {
    // ADR-036 §3.7 — route Save by active tab kind.
    if (activeFileTab) {
      if (!activeFileTab.readOnly) {
        void saveFileTab(activeFileTab.id).catch((error) => {
          console.warn(`saveFileTab(${activeFileTab.id}) failed:`, error);
        });
      }
    } else {
      void saveWorkflow();
    }
  }, [activeFileTab, saveFileTab, saveWorkflow]);

  return { handleAddBlockFromPalette, handleCanvasConnect, handleViewSource, handleSave };
}
