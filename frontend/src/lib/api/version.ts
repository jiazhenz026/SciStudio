/**
 * ADR-045 workflow-state version-vector types + client-side source-id
 * tracking helpers.
 *
 * Originally added inline to `frontend/src/lib/api.ts` by PR #1410.
 * Hoisted into its own module during the #1426 main-merge so the
 * post-#1422 `api/<domain>.ts` split keeps the shell thin while still
 * exposing the same surface (`import { ... } from "../lib/api"`) to
 * downstream consumers.
 */

import type { WorkflowResponse } from "../../types/api";

export type VersionedWorkflowResponse = WorkflowResponse & {
  state_version?: number;
  workflow_version?: string;
  entity_class?: "workflow";
  entity_id?: string;
  source?: string | null;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
};

export interface ProjectFileResponse {
  content: string;
  mtime: number;
  size: number;
  encoding: string;
  state_version?: number;
  entity_class?: "file";
  entity_id?: string;
  source?: string | null;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
}

export interface ProjectFileWriteResponse {
  mtime: number;
  size: number;
  state_version?: number;
  entity_class?: "file";
  entity_id?: string;
  source?: string;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
}

export interface VersionedWriteOptions {
  sourceId?: string;
  source?: "canvas" | "agent" | "gitRestore" | "import" | "external" | string;
  createParentDirs?: boolean;
}

const pendingWorkflowSourceIds = new Map<string, Set<string>>();
let workflowWriteStartedListener: ((workflowId: string, sourceId: string) => void) | null = null;

export function createClientSourceId(prefix: "workflow" | "file"): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  const token =
    typeof randomUUID === "function"
      ? randomUUID.call(globalThis.crypto)
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${token}`;
}

export function setWorkflowWriteStartedListener(
  listener: ((workflowId: string, sourceId: string) => void) | null,
): void {
  workflowWriteStartedListener = listener;
}

export function rememberPendingWorkflowSourceId(workflowId: string, sourceId: string): void {
  const existing = pendingWorkflowSourceIds.get(workflowId) ?? new Set<string>();
  existing.add(sourceId);
  pendingWorkflowSourceIds.set(workflowId, existing);
  workflowWriteStartedListener?.(workflowId, sourceId);
}

export function consumePendingWorkflowSourceId(
  workflowId: string,
  sourceId: string | null,
): boolean {
  if (!sourceId) return false;
  const existing = pendingWorkflowSourceIds.get(workflowId);
  if (!existing?.has(sourceId)) return false;
  existing.delete(sourceId);
  if (existing.size === 0) pendingWorkflowSourceIds.delete(workflowId);
  return true;
}
