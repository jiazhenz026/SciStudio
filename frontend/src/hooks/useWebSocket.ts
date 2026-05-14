import { useEffect, useRef, useState, useCallback } from "react";

import { api } from "../lib/api";
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
  const bumpUnreadProblems = useAppStore((state) => state.bumpUnreadProblems);
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

      // #591/#594: Handle interactive_prompt events from backend.
      if (payload.type === "interactive_prompt") {
        setInteractivePrompt({
          blockId: payload.block_id ?? "",
          blockType: (payload.data.block_type as string) ?? "",
          data: payload.data,
        });
        return;
      }

      // ADR-034 Phase 2: filesystem watcher emits ``workflow.changed`` when
      // an external editor (or claude/codex via MCP) mutates a workflow YAML.
      // If the change targets the workflow currently loaded in the canvas,
      // refetch it and replace the in-memory state. If the file was deleted,
      // clear the canvas and warn via the Logs panel.
      if (payload.type === "workflow.changed") {
        const changedId =
          (payload.workflow_id as string | null | undefined) ??
          (payload.data.workflow_id as string | undefined) ??
          null;
        const kind = (payload.data.kind as string | undefined) ?? "modified";
        // Any workflow YAML touch on disk is also a project-tree change,
        // so kick the ProjectTree's auto-refresh signal. The actual file
        // tree refetch happens in ProjectTree's useEffect subscribed to
        // ``projectTreeRefreshCounter``.
        useAppStore.getState().bumpProjectTreeRefresh();
        // ADR-034: agent-driven ``write_workflow`` (kind=created) for a
        // workflow that isn't already open as a tab — auto-open it so
        // the user can see what claude/codex just produced without
        // having to navigate the file tree manually.
        if (
          changedId &&
          kind === "created" &&
          !useAppStore.getState().tabs.some((t) => t.workflowId === changedId)
        ) {
          api
            .getWorkflow(changedId)
            .then((fresh) => {
              useAppStore.getState().openTab(fresh, changedId);
            })
            .catch(() => {
              // best-effort; user can still open it via the file tree
            });
          return;
        }
        const currentId = useAppStore.getState().workflowId;
        if (changedId && changedId === currentId) {
          if (kind === "deleted" || kind === "moved") {
            setWorkflow(null);
            appendLog({
              timestamp: payload.timestamp,
              level: "warn",
              message: `Workflow '${changedId}' was ${kind} on disk; canvas cleared.`,
              workflow_id: changedId,
              block_id: null,
            });
          } else {
            // modified / created — refetch and replace.
            api
              .getWorkflow(changedId)
              .then((fresh) => {
                // Re-check inside the resolution: the user may have switched
                // workflows while the fetch was in flight.
                if (useAppStore.getState().workflowId === changedId) {
                  setWorkflow(fresh);
                }
              })
              .catch((err) => {
                appendLog({
                  timestamp: payload.timestamp,
                  level: "error",
                  message: `Failed to refresh workflow '${changedId}' after disk change: ${
                    err instanceof Error ? err.message : String(err)
                  }`,
                  workflow_id: changedId,
                  block_id: null,
                });
              });
          }
        }
        // Mismatched id: ignore (workflow lives in another tab or is not loaded).
        return;
      }

      consumeEvent(payload);

      // #793: Do NOT force-switch the bottom panel to "logs" on engine events.
      // The user's directive is "never auto-switch". The Logs unread badge
      // is now coupled to ``appendLog`` itself (executionSlice) so it tracks
      // actual rendered rows, not "any event the WS saw" — that previously
      // produced the "N unread but Logs panel is empty" mismatch.
      //
      // Problems still tracks block_error specifically: it's a fault counter,
      // not a log-row counter, and there's exactly one Problems row per
      // block_error event.
      if (payload.type === "block_error" && typeof payload.data.error === "string") {
        bumpUnreadProblems();
      }
    };

    return () => {
      socket.close();
      _activeSocket = null;
    };
  }, [appendLog, bumpUnreadProblems, consumeEvent, enabled, setInteractivePrompt, setWorkflow]);

  return { connected };
}
