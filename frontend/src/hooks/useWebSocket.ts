import { useEffect, useState } from "react";

import { useAppStore } from "../store";
import type { WorkflowEventMessage } from "../types/api";
import { dispatchWorkflowEvent } from "./useWebSocket.parts/dispatchEvent";

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
  const setWorkflow = useAppStore((state) => state.setWorkflow);
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
      const consumed = dispatchWorkflowEvent(payload, {
        appendLog,
        setInteractivePrompt,
        setWorkflow,
      });
      if (consumed) return;

      consumeEvent(payload);

      // The Logs unread badge is coupled to ``appendLog`` / ``consumeEvent``
      // itself (executionSlice) so it tracks actual rendered rows. The
      // Problems tab was removed in the same change set — block_error rows
      // surface in the Logs panel (filterable via the level selector) and
      // as the inline error badge on the BlockNode itself.
    };

    return () => {
      socket.close();
      _activeSocket = null;
    };
  }, [appendLog, consumeEvent, enabled, setInteractivePrompt, setWorkflow]);

  return { connected };
}
