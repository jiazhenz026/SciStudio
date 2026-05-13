/**
 * Agent chat WebSocket hook.
 *
 * Owns the lifecycle of a single `/api/ai/chat/{chatId}?project_dir=...`
 * connection. Parses every inbound frame against the protocol envelope
 * discriminators defined in `scieasy.api.schemas`:
 *
 *  - `agent_event`        → `appendEvent` into `aiChatSlice`
 *  - `permission_request` → `setPendingPermission`
 *  - `session_ended`      → `markSessionEnded`
 *  - `error`              → appended as a synthetic `"error"` AgentEvent
 *
 * Outbound frames are typed via `OutboundMessage`. Reconnect uses
 * exponential backoff capped at 8s. Components call `sendMessage` /
 * `cancel` / `sendPermissionDecision`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useAppStore } from "../store";
import type { AgentEvent, PermissionDecision } from "../types/agentEvents";

/** WS connection state surfaced to UI. */
export type WSConnectionState = "idle" | "connecting" | "open" | "closed" | "reconnecting";

type OutboundUserMessage = { type: "user_message"; content: string };
type OutboundCancel = { type: "cancel" };
type OutboundPermissionDecision = {
  type: "permission_decision";
  request_id: string;
  decision: PermissionDecision;
};
type OutboundMessage = OutboundUserMessage | OutboundCancel | OutboundPermissionDecision;

export interface UseAgentWebSocketResult {
  /** Connection lifecycle state for UI banners. */
  state: WSConnectionState;
  /** Send a user message to the agent. */
  sendMessage: (content: string) => boolean;
  /** Cancel the in-flight agent turn. */
  cancel: () => boolean;
  /** Send the user's decision for a pending permission prompt. */
  sendPermissionDecision: (requestId: string, decision: PermissionDecision) => boolean;
}

/** Initial reconnect delay in ms; doubles each failure, capped at 8s. */
const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 8000;

/**
 * Open and manage a chat WebSocket for the given chat id.
 *
 * @param chatId - active chat id; when null, no socket is opened.
 * @param projectDir - absolute path of the SciEasy project workspace; the
 *   backend validates this against an allow-list before spawning the agent.
 */
export function useAgentWebSocket(
  chatId: string | null,
  projectDir: string | null,
): UseAgentWebSocketResult {
  const appendEvent = useAppStore((s) => s.appendEvent);
  const setPendingPermission = useAppStore((s) => s.setPendingPermission);
  const markSessionEnded = useAppStore((s) => s.markSessionEnded);

  const [state, setState] = useState<WSConnectionState>("idle");
  const socketRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef<boolean>(false);

  useEffect(() => {
    if (!chatId || !projectDir) {
      setState("idle");
      return undefined;
    }
    // Per-effect cancellation flag. Captured by each WebSocket's onclose
    // closure so that stale close events (from a socket whose effect has
    // already been torn down by a chatId / projectDir change) cannot
    // schedule a reconnect for the wrong chat. See PR #745 Codex P1.
    let cancelled = false;
    intentionalCloseRef.current = false;

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const qs = `project_dir=${encodeURIComponent(projectDir)}`;
      const url = `${proto}://${window.location.host}/api/ai/chat/${encodeURIComponent(chatId)}?${qs}`;
      const ws = new WebSocket(url);
      socketRef.current = ws;
      setState((prev) => (prev === "open" || prev === "connecting" ? prev : "connecting"));

      ws.onopen = () => {
        backoffRef.current = INITIAL_BACKOFF_MS;
        setState("open");
      };
      ws.onmessage = (msg) => {
        try {
          const payload = JSON.parse(msg.data) as { type?: string } & Record<string, unknown>;
          switch (payload.type) {
            case "agent_event": {
              const event = payload.event as AgentEvent | undefined;
              if (event !== undefined) {
                appendEvent(chatId, event);
              }
              break;
            }
            case "permission_request": {
              const requestId = String(payload.request_id ?? "");
              const tool = (payload.tool ?? {}) as {
                name?: string;
                input?: Record<string, unknown>;
              };
              if (requestId) {
                setPendingPermission(chatId, {
                  requestId,
                  toolName: tool.name ?? "",
                  toolInput: tool.input ?? {},
                });
              }
              break;
            }
            case "session_ended": {
              markSessionEnded(chatId);
              break;
            }
            case "error": {
              // Surface server-reported errors as synthetic AgentEvents
              // so they render inline alongside the conversation.
              const message = String(payload.message ?? "unknown error");
              appendEvent(chatId, {
                kind: "error",
                raw: payload,
                message,
                error_type: null,
              });
              break;
            }
            default:
              // eslint-disable-next-line no-console
              console.warn("useAgentWebSocket: unknown envelope type", payload.type);
          }
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error("useAgentWebSocket: failed to parse message", err);
        }
      };
      ws.onerror = () => {
        // onclose follows onerror — let onclose drive reconnect logic.
      };
      ws.onclose = () => {
        socketRef.current = null;
        // If this effect has already been torn down (chatId / projectDir
        // changed), this onclose is stale. Do not reconnect — the new
        // effect owns the new socket.
        if (cancelled || intentionalCloseRef.current) {
          setState("closed");
          return;
        }
        setState("reconnecting");
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          if (cancelled) return;
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = socketRef.current;
      socketRef.current = null;
      if (ws !== null && ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
    };
  }, [chatId, projectDir, appendEvent, setPendingPermission, markSessionEnded]);

  const send = useCallback((message: OutboundMessage): boolean => {
    const ws = socketRef.current;
    if (ws === null || ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    ws.send(JSON.stringify(message));
    return true;
  }, []);

  const sendMessage = useCallback(
    (content: string): boolean => send({ type: "user_message", content }),
    [send],
  );
  const cancel = useCallback((): boolean => send({ type: "cancel" }), [send]);
  const sendPermissionDecision = useCallback(
    (requestId: string, decision: PermissionDecision): boolean =>
      send({ type: "permission_decision", request_id: requestId, decision }),
    [send],
  );

  return { state, sendMessage, cancel, sendPermissionDecision };
}
