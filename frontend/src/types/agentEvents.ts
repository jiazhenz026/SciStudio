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
  /** Canonical event kind discriminator (literal on each known subclass). */
  kind: AgentEventKind;
  /** Original parsed JSON payload from the provider stream. */
  raw: AgentEventRaw;
}

/** Canonical, frontend-recognised event kinds. */
export type KnownAgentEventKind =
  | "init"
  | "assistant_text_delta"
  | "tool_use"
  | "tool_result"
  | "permission_request"
  | "error"
  | "done"
  | "other";

/**
 * Back-compat alias. New code should use :data:`KnownAgentEventKind`.
 *
 * The frontend tolerates any string `kind` (future provider kinds flow
 * through unchanged via :class:`OtherEvent`); narrowing still works on
 * the canonical branches because each typed subclass declares its own
 * literal `kind`.
 */
export type AgentEventKind = KnownAgentEventKind;

/**
 * Generic UI rendering taxonomy carried on :class:`OtherEvent` (issue #788).
 *
 * Backend (`scieasy.ai.agent.provider.DisplayClass`) is the source of truth.
 * See `src/scieasy/ai/agent/stream_json.py:classify_for_display`.
 */
export type DisplayClass = "hidden" | "meta" | "text-like" | "tool-like" | "raw";

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

/**
 * Catch-all for unknown event kinds; original payload preserved in `raw`.
 *
 * The TypeScript discriminator is the literal `"other"` so narrowing on
 * the canonical branches (`init` / `tool_use` / ...) keeps working. The
 * actual wire-format kind the backend received (e.g. `"thinking"`,
 * `"system/hook_started"`, future provider kinds) is preserved in
 * :prop:`raw.kind` (and historically `raw.type`). For runtime checks
 * the renderer reads `(event.kind as string)` or `raw.kind`/`raw.type`
 * — see :func:`getOtherKind`.
 *
 * Issue #788: `display_class` is the generic rendering taxonomy the
 * backend computes via `classify_for_display`. Optional so legacy /
 * test fixtures that omit it default to a safe `raw` rendering.
 */
export interface OtherEvent extends AgentEventBase {
  // The runtime value may be any string (the backend preserves the wire
  // kind); the type-system discriminator is a literal so narrowing works.
  kind: "other";
  display_class?: DisplayClass;
}

/**
 * Extract the wire-format kind from an :class:`OtherEvent`. At runtime
 * the backend sets `event.kind` to the wire kind (e.g. `"thinking"`);
 * the TS literal `"other"` declared above is a discriminator hint, not
 * the runtime value. This helper papers over the gap.
 */
export function getOtherKind(event: OtherEvent): string {
  const k = (event as { kind?: string }).kind;
  if (typeof k === "string" && k !== "other") return k;
  const rawKind = (event.raw as { kind?: unknown }).kind;
  if (typeof rawKind === "string") return rawKind;
  const rawType = (event.raw as { type?: unknown }).type;
  if (typeof rawType === "string") return rawType;
  return "other";
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
