import { useEffect, useRef, useState, useCallback } from "react";

import type { WorkflowEventMessage } from "../types/api";
import { useAppStore } from "../store";

/** Ref-holder for the active WebSocket so components can send messages. */
let _activeSocket: WebSocket | null = null;

/** Send a JSON message over the active WebSocket connection.
 *  Returns false if the socket is not connected. */
export function sendWebSocketMessage(message: Record<string, unknown>): boolean {
  if (_activeSocket && _activeSocket.readyState === WebSocket.OPEN) {
    _activeSocket.send(JSON.stringify(message));
    return true;
  }
  return false;
}

export function useWorkflowWebSocket(enabled: boolean): { connected: boolean } {
  const consumeEvent = useAppStore((state) => state.consumeEvent);
  const appendLog = useAppStore((state) => state.appendLog);
  const setInteractivePrompt = useAppStore((state) => state.setInteractivePrompt);
  const bumpUnreadLogs = useAppStore((state) => state.bumpUnreadLogs);
  const bumpUnreadProblems = useAppStore((state) => state.bumpUnreadProblems);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
    _activeSocket = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => {
      setConnected(false);
      _activeSocket = null;
    };
    socket.onerror = () => {
      setConnected(false);
      _activeSocket = null;
    };
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as WorkflowEventMessage;

      // #591/#594: Handle interactive_prompt events from backend.
      if (payload.type === "interactive_prompt") {
        setInteractivePrompt({
          blockId: payload.block_id ?? "",
          blockType: (payload.data.block_type as string) ?? "",
          data: payload.data,
        });
        return;
      }

      consumeEvent(payload);

      // #793: Do NOT force-switch the bottom panel to "logs" on engine events.
      // The user's directive is "never auto-switch". Instead, bump an unread
      // counter so the Logs / Problems tab gets a small badge while the user
      // is on a different tab — they decide when to look.
      if (payload.type.startsWith("block_") || payload.type.startsWith("workflow_")) {
        bumpUnreadLogs();
      }

      // Append a dedicated log entry for block_error events so the full error
      // text is visible in the Logs panel even if the user missed the node badge.
      if (payload.type === "block_error" && typeof payload.data.error === "string") {
        appendLog({
          timestamp: payload.timestamp,
          level: "error",
          message: `Block error [${payload.block_id ?? "unknown"}]: ${payload.data.error}`,
          workflow_id: payload.workflow_id ?? null,
          block_id: payload.block_id ?? null,
        });
        bumpUnreadProblems();
      }
    };

    return () => {
      socket.close();
      _activeSocket = null;
    };
  }, [appendLog, bumpUnreadLogs, bumpUnreadProblems, consumeEvent, enabled, setInteractivePrompt]);

  return { connected };
}
