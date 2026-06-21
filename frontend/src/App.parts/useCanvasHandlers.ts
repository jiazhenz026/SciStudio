// Extracted from App.tsx as part of the #1422 god-file split.
//
// useCanvasHandlers — the callbacks the workflow canvas + toolbar dispatch
// when the user clicks "Add Block" in the palette, drags an edge between
// two ports, asks for the workflow YAML ("View source"), or hits the
// global Save button. These are all bound handlers that exist purely to
// keep App.tsx focused on the render tree and lifecycle.

import { useCallback } from "react";

import { resolveVariadicPorts } from "../components/WorkflowCanvas.parts/flowNodeBuilder";
import { api } from "../lib/api";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  BlockSummary,
  ProjectResponse,
  WorkflowEdge,
  WorkflowNode,
} from "../types/api";
import type { FileTab } from "../store/types";
import { computeEffectivePorts } from "../utils/computeEffectivePorts";

// Resolve a source node's effective output port type, mirroring how the canvas
// colours edges: variadic blocks read their declared ``output_ports`` types,
// dynamic blocks (e.g. LoadData) resolve via ``dynamic_ports`` + config. Returns
// the primary type name, or ``undefined`` when it cannot be resolved.
function effectiveOutputType(
  node: WorkflowNode,
  portName: string,
  schemas: Record<string, BlockSchemaResponse>,
): string | undefined {
  const schema = schemas[node.block_type];
  if (!schema) return undefined;
  const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
  let ports: BlockPortResponse[];
  if (schema.variadic_outputs) {
    ports = resolveVariadicPorts(schema.output_ports ?? [], params, "output", schema);
  } else {
    const cfgKey = schema.dynamic_ports?.source_config_key as string | undefined;
    const cfgVal = cfgKey ? String(params[cfgKey] ?? "") : undefined;
    ports = computeEffectivePorts(
      schema.dynamic_ports ?? null,
      cfgVal,
      schema.output_ports ?? [],
      "output",
    );
  }
  return ports.find((port) => port.name === portName)?.accepted_types?.[0];
}

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
  schemas: Record<string, BlockSchemaResponse>;
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
    schemas,
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
        // MergeCollection requires both inputs to carry the same Collection
        // item type (the backend ``run`` raises on mismatch). Each edge alone is
        // type-valid (both inputs accept DataObject), so enforce the cross-input
        // constraint here at connect time: if the other input is already wired to
        // a concrete, different type, reject the connection with a banner — the
        // same "can't connect + top banner" pattern as the cycle/type checks.
        if (
          targetNode.block_type === "mergecollection_block" &&
          (targetPort === "input_a" || targetPort === "input_b")
        ) {
          const otherPort = targetPort === "input_a" ? "input_b" : "input_a";
          const otherEdge = workflowEdges.find((candidate) => {
            const [otherTargetNode, otherTargetPort] = candidate.target.split(":");
            return otherTargetNode === targetNode.id && otherTargetPort === otherPort;
          });
          if (otherEdge) {
            const [otherSourceId, otherSourcePort] = otherEdge.source.split(":");
            const otherSourceNode = workflowNodes.find((node) => node.id === otherSourceId);
            const newType = effectiveOutputType(sourceNode, sourcePort, schemas);
            const otherType = otherSourceNode
              ? effectiveOutputType(otherSourceNode, otherSourcePort, schemas)
              : undefined;
            if (
              newType &&
              otherType &&
              newType !== "DataObject" &&
              otherType !== "DataObject" &&
              newType !== otherType
            ) {
              setLastError(
                `MergeCollection inputs must be the same Collection type: ${otherType} vs ${newType}.`,
              );
              return;
            }
          }
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
    [connectNodes, setLastError, workflowNodes, workflowEdges, schemas],
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
