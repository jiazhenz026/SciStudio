import { useEffect, useState } from "react";

import { useAppStore } from "../store";
import type { WorkflowEventMessage } from "../types/api";
import {
  RECONNECT_INITIAL_DELAY_MS,
  nextBackoffDelay,
  type ConnectionStatus,
} from "./connectionState";
import { dispatchWorkflowEvent } from "./useWebSocket.parts/dispatchEvent";

/** Heartbeat interval (#177): ping the server to detect stale sockets. */
const HEARTBEAT_INTERVAL_MS = 30000;

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

export interface WorkflowWebSocketState {
  connected: boolean;
  /** #177: richer lifecycle so the UI can show reconnecting. */
  status: ConnectionStatus;
}

/**
 * Maintain the workflow WebSocket connection.
 *
 * #177: the socket is recreated with exponential backoff after any
 * ``onclose`` / ``onerror`` so a dropped connection does not silently
 * stop block-state updates and log streaming. A 30s ping heartbeat
 * detects half-open sockets (e.g. laptop sleep/wake) that never fire a
 * close event; if no pong is observed before the next interval the
 * socket is force-closed, which triggers the reconnect path. The
 * backoff resets to :data:`RECONNECT_INITIAL_DELAY_MS` after a
 * successful open.
 *
 * The returned ``status`` is component state for the UI indicator only;
 * it is not runtime truth and is never persisted to the store.
 */
export function useWorkflowWebSocket(enabled: boolean): WorkflowWebSocketState {
  const consumeEvent = useAppStore((state) => state.consumeEvent);
  const appendLog = useAppStore((state) => state.appendLog);
  const setInteractivePrompt = useAppStore((state) => state.setInteractivePrompt);
  const setWorkflow = useAppStore((state) => state.setWorkflow);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");

  useEffect(() => {
    if (!enabled) {
      setStatus("disconnected");
      return undefined;
    }

    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    let delay = RECONNECT_INITIAL_DELAY_MS;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${protocol}://${window.location.host}/ws`;

    const clearHeartbeat = () => {
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    };

    // #177 heartbeat. The SciStudio backend WS handler does NOT implement
    // an application-level ping/pong (its inbound loop logs unknown frame
    // types and never replies — see `src/scistudio/api/ws.py`), and that
    // module is frozen by ADR-035/036 scope. So we MUST NOT rely on a
    // server pong to judge liveness — doing so would force-close a
    // perfectly healthy socket every interval.
    //
    // Instead the heartbeat detects the half-open case (laptop sleep/wake,
    // network handoff) where the browser has moved the socket out of OPEN
    // without yet firing `onclose`: if `readyState` is no longer OPEN we
    // force-close so the managed reconnect path runs promptly rather than
    // waiting for the browser's own (sometimes very delayed) close event.
    const startHeartbeat = () => {
      clearHeartbeat();
      heartbeatTimer = setInterval(() => {
        if (cancelled || !socket) return;
        if (socket.readyState !== WebSocket.OPEN) {
          // Stale / half-open socket — drive the reconnect now.
          handleClosed();
        }
      }, HEARTBEAT_INTERVAL_MS);
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      setStatus("reconnecting");
      retryTimer = setTimeout(() => {
        delay = nextBackoffDelay(delay);
        connect();
      }, delay);
    };

    const handleClosed = () => {
      clearHeartbeat();
      if (_activeSocket === socket) _activeSocket = null;
      socket = null;
      if (cancelled) return;
      scheduleReconnect();
    };

    function connect() {
      if (cancelled) return;
      socket = new WebSocket(url);
      _activeSocket = socket;

      socket.onopen = () => {
        if (cancelled) return;
        delay = RECONNECT_INITIAL_DELAY_MS;
        setStatus("connected");
        startHeartbeat();
      };
      socket.onclose = handleClosed;
      socket.onerror = () => {
        // Defer to onclose for reconnect; browsers fire error then close.
        // If error fires without a subsequent close, the heartbeat will
        // eventually force one.
        if (socket && socket.readyState === WebSocket.CLOSED) {
          handleClosed();
        }
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
    }

    setStatus("connecting");
    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      clearHeartbeat();
      if (socket) {
        // Detach handlers so teardown does not schedule a reconnect.
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
      if (_activeSocket === socket) _activeSocket = null;
      socket = null;
      setStatus("disconnected");
    };
  }, [appendLog, consumeEvent, enabled, setInteractivePrompt, setWorkflow]);

  return { connected: status === "connected", status };
}
