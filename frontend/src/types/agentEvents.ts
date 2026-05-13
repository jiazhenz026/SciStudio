/**
 * TypeScript discriminated union mirroring the canonical agent event
 * taxonomy defined in `src/scieasy/ai/agent/provider.py` (Phase 1).
 *
 * This file is the single source of truth on the frontend for the
 * shape of `agent_event` payloads delivered over the chat WebSocket.
 * It is NOT a stub: T-ECA-303 implementations rely on it being typed
 * correctly.
 *
 * Update protocol: if the Python dataclasses in `provider.py` gain or
 * lose a field, mirror the change here in the same PR. The backend
 * envelope schema lives in `scieasy.api.schemas` (added in T-ECA-302).
 */

/** Catch-all for forensic logging of provider-specific fields. */
export type AgentEventRaw = Record<string, unknown>;

export interface AgentEventBase {
  /** Canonical event kind discriminator. */
  kind: AgentEventKind;
  /** Original parsed JSON payload from the provider stream. */
  raw: AgentEventRaw;
}

export type AgentEventKind =
  | "init"
  | "assistant_text_delta"
  | "tool_use"
  | "tool_result"
  | "permission_request"
  | "error"
  | "done"
  | "other";

/** First event in every session; carries the provider-assigned session id. */
export interface InitEvent extends AgentEventBase {
  kind: "init";
  session_id: string;
  schema_version: string | null;
  model: string | null;
}

/** Streaming assistant-text chunk. Concatenate consecutive deltas. */
export interface AssistantTextDeltaEvent extends AgentEventBase {
  kind: "assistant_text_delta";
  delta: string;
}

/** Agent announced a tool invocation. */
export interface ToolUseEvent extends AgentEventBase {
  kind: "tool_use";
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_use_id: string;
}

/** Result of a previously announced tool invocation. */
export interface ToolResultEvent extends AgentEventBase {
  kind: "tool_result";
  tool_use_id: string;
  output: string | Record<string, unknown>;
  is_error: boolean;
}

/**
 * Synthetic event surfaced by the hook bridge when user approval is required.
 * Claude Code emits this through the PreToolUse hook, not the raw stream-json.
 */
export interface PermissionRequestEvent extends AgentEventBase {
  kind: "permission_request";
  tool_name: string;
  tool_input: Record<string, unknown>;
  request_id: string;
}

/** Stream-level error reported by the provider subprocess. */
export interface ErrorEvent extends AgentEventBase {
  kind: "error";
  message: string;
  error_type: string | null;
}

/** Terminal event marking the end of an agent turn. */
export interface DoneEvent extends AgentEventBase {
  kind: "done";
}

/** Catch-all for unknown event kinds; original payload preserved in `raw`. */
export interface OtherEvent extends AgentEventBase {
  kind: "other";
}

/** Discriminated union of all canonical agent events. */
export type AgentEvent =
  | InitEvent
  | AssistantTextDeltaEvent
  | ToolUseEvent
  | ToolResultEvent
  | PermissionRequestEvent
  | ErrorEvent
  | DoneEvent
  | OtherEvent;

/** Permission-decision values exchanged over the WS protocol. */
export type PermissionDecision = "approve" | "deny";

/** Permission policy modes; mirrors `PermissionMode` enum in `provider.py`. */
export type PermissionMode = "strict" | "bypass";
