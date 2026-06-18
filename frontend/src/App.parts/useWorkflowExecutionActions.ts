// Extracted from App.tsx as part of the #1422 god-file split.
//
// useWorkflowExecutionActions — bundles the run / pause / resume / cancel /
// startFromSelected / per-block run+restart callbacks the toolbar and the
// workflow canvas dispatch. Each action keeps the same shape and
// side-effects as the inline implementation; this hook merely consolidates
// them so App.tsx can stay focused on lifecycle wiring.

import { useCallback } from "react";

import { api } from "../lib/api";
import type {
  BlockSchemaResponse,
  FormatCapabilityResponse,
  ProjectResponse,
  WorkflowNode,
} from "../types/api";

export interface WorkflowExecutionDeps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  selectedNodeId: string | null;
  saveWorkflow: () => Promise<void>;
  setLastError: (message: string | null) => void;
  workflowPayloadId: string;
  workflowNodes?: WorkflowNode[];
  blockSchemas?: Record<string, BlockSchemaResponse>;
}

export interface WorkflowExecutionActions {
  runWorkflow: () => Promise<void>;
  pauseWorkflow: () => Promise<void>;
  resumeWorkflow: () => Promise<void>;
  cancelWorkflow: () => Promise<void>;
  startFromSelected: () => Promise<void>;
  handleRunBlock: (blockId: string) => Promise<void>;
  handleRestartBlock: (blockId: string) => Promise<void>;
}

function surfaceExecutionError(
  setLastError: (message: string | null) => void,
  error: unknown,
): void {
  const message = error instanceof Error ? error.message : String(error);
  window.setTimeout(() => setLastError(message), 0);
}

function pathJoin(dir: string, name: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir.replace(/[\\/]+$/, "")}${sep}${name}`;
}

function pathHasExtension(path: string): boolean {
  const name =
    path
      .replace(/[\\/]+$/, "")
      .split(/[\\/]/)
      .pop() ?? "";
  return /\.[^./\\]+$/.test(name);
}

function capabilityForNode(
  node: WorkflowNode,
  schema: BlockSchemaResponse | undefined,
): FormatCapabilityResponse | undefined {
  const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
  const selectedType =
    typeof params.core_type === "string"
      ? params.core_type
      : typeof schema?.config_schema.properties?.core_type?.default === "string"
        ? schema.config_schema.properties.core_type.default
        : "";
  const capabilities = (schema?.format_capabilities ?? []).filter(
    (capability) => capability.direction === "save" && capability.data_type === selectedType,
  );
  const capabilityId = params.capability_id;
  if (typeof capabilityId === "string") {
    const selected = capabilities.find((capability) => capability.id === capabilityId);
    if (selected) return selected;
  }
  return capabilities.find((capability) => capability.is_default) ?? capabilities[0];
}

function filenameForNode(
  node: WorkflowNode,
  schema: BlockSchemaResponse | undefined,
): string | null {
  const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
  const capability = capabilityForNode(node, schema);
  const extension = capability?.extensions[0] ?? "";
  const coreType =
    typeof params.core_type === "string"
      ? params.core_type
      : typeof schema?.config_schema.properties?.core_type?.default === "string"
        ? schema.config_schema.properties.core_type.default
        : "data";
  const raw =
    typeof params.filename === "string" && params.filename.trim() ? params.filename.trim() : "";
  const base = raw ? raw.split(/[\\/]/).pop() || raw : `${coreType.toLowerCase()}${extension}`;
  if (!extension || pathHasExtension(base)) return base;
  return `${base}${extension}`;
}

async function confirmOverwriteNodes(
  nodes: WorkflowNode[],
  schemas: Record<string, BlockSchemaResponse>,
): Promise<string[]> {
  const hits: Array<{ nodeId: string; path: string }> = [];
  for (const node of nodes) {
    if (node.block_type !== "save_data") continue;
    const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
    if (params.overwrite === true || typeof params.path !== "string" || !params.path.trim())
      continue;
    const schema = schemas[node.block_type];
    const pathStat = await api.statFilesystem(params.path).catch(() => null);
    let target = params.path;
    if (pathStat?.exists && pathStat.type === "directory") {
      const filename = filenameForNode(node, schema);
      if (!filename) continue;
      target = pathJoin(params.path, filename);
    } else if (!pathHasExtension(target)) {
      const capability = capabilityForNode(node, schema);
      const extension = capability?.extensions[0] ?? "";
      if (extension) target = `${target}${extension}`;
    }
    const targetStat = await api.statFilesystem(target).catch(() => null);
    if (targetStat?.exists) hits.push({ nodeId: node.id, path: target });
  }
  if (hits.length === 0) return [];
  const message = [
    "The following Save outputs already exist. Overwrite them?",
    "",
    ...hits.map((hit) => hit.path),
  ].join("\n");
  return window.confirm(message) ? hits.map((hit) => hit.nodeId) : ["__cancel__"];
}

export function useWorkflowExecutionActions(deps: WorkflowExecutionDeps): WorkflowExecutionActions {
  const {
    currentProject,
    workflowId,
    selectedNodeId,
    saveWorkflow,
    setLastError,
    workflowPayloadId,
    workflowNodes = [],
    blockSchemas = {},
  } = deps;

  const runWorkflow = useCallback(async () => {
    if (!currentProject) return;
    try {
      await saveWorkflow();
      const overwriteNodeIds = await confirmOverwriteNodes(workflowNodes, blockSchemas);
      if (overwriteNodeIds.includes("__cancel__")) return;
      await api.executeWorkflow(workflowPayloadId, { overwriteNodeIds });
      setLastError(null);
      // #793: do NOT auto-switch to the Logs tab.
    } catch (error) {
      surfaceExecutionError(setLastError, error);
    }
  }, [blockSchemas, currentProject, saveWorkflow, setLastError, workflowNodes, workflowPayloadId]);

  const pauseWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.pauseWorkflow(workflowId);
  }, [workflowId]);

  const resumeWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.resumeWorkflow(workflowId);
  }, [workflowId]);

  const cancelWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.cancelWorkflow(workflowId);
  }, [workflowId]);

  const startFromSelected = useCallback(async () => {
    if (!workflowId || !selectedNodeId) return;
    try {
      await saveWorkflow();
      const overwriteNodeIds = await confirmOverwriteNodes(workflowNodes, blockSchemas);
      if (overwriteNodeIds.includes("__cancel__")) return;
      await api.executeFrom(workflowId, selectedNodeId, { overwriteNodeIds });
      setLastError(null);
    } catch (error) {
      surfaceExecutionError(setLastError, error);
    }
  }, [blockSchemas, saveWorkflow, selectedNodeId, setLastError, workflowId, workflowNodes]);

  const handleRunBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        const overwriteNodeIds = await confirmOverwriteNodes(workflowNodes, blockSchemas);
        if (overwriteNodeIds.includes("__cancel__")) return;
        await api.executeFrom(workflowId, blockId, { overwriteNodeIds });
        setLastError(null);
      } catch (error) {
        surfaceExecutionError(setLastError, error);
      }
    },
    [blockSchemas, saveWorkflow, setLastError, workflowId, workflowNodes],
  );

  const handleRestartBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        const overwriteNodeIds = await confirmOverwriteNodes(workflowNodes, blockSchemas);
        if (overwriteNodeIds.includes("__cancel__")) return;
        await api.executeFrom(workflowId, blockId, { overwriteNodeIds });
        setLastError(null);
      } catch (error) {
        surfaceExecutionError(setLastError, error);
      }
    },
    [blockSchemas, saveWorkflow, setLastError, workflowId, workflowNodes],
  );

  return {
    runWorkflow,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    startFromSelected,
    handleRunBlock,
    handleRestartBlock,
  };
}
