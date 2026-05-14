import { useEffect, useRef, useState, useCallback } from "react";

import {
  handleBlockPtyClosed,
  handleBlockPtyOpened,
} from "../components/AIChat/blockPtyHandlers";
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

      // ADR-035 §3.10 skeleton: engine-initiated PTY tab open/close events
      // for AI Block runs. Implementation phase (I35c) wires these to the
      // TerminalTabs component's `handleBlockPtyOpened` /
      // `handleBlockPtyClosed` helpers, which create / update the tab in
      // the Zustand `terminalTabsSlice`.
      //
      // Implementation plan (I35c):
      //   1. Import handleBlockPtyOpened / handleBlockPtyClosed from
      //      ../components/AIChat/TerminalTabs.
      //   2. On `block_pty_opened`: validate payload shape, call handler.
      //   3. On `block_pty_closed`: validate payload shape, call handler.
      //   4. Both events should also append a Logs entry so the user sees
      //      ``[AI Block: extract_metadata] tab opened`` / ``... completed``
      //      in the Logs panel for traceability per ADR-035 §6.1 (lineage).
      //
      // Test plan (vitest):
      //   - test_block_pty_opened_dispatches_to_handler
      //   - test_block_pty_closed_dispatches_to_handler
      //   - test_unknown_payload_shape_logs_warning_does_not_throw
      //
      // References: ADR-035 §3.10, §6.1
      if (payload.type === "block_pty_opened") {
        try {
          // The wire payload may live at the top level OR nested under `data`,
          // depending on which engine path emitted it. Tolerate both.
          const src = (payload.data ?? {}) as Record<string, unknown>;
          const top = payload as unknown as Record<string, unknown>;
          // Audit P2-A (Codex #866-2): backend emits ``permission_mode`` at
          // the top level of the message (see ``ai_pty.open_engine_initiated_tab``
          // line 507). Reading from ``src.permission_mode`` always returned
          // undefined, silently downgrading bypass-mode tabs to "safe".
          // Mirror the resilience pattern used for tab_id / block_run_id —
          // prefer the top-level field, fall back to nested for older paths.
          handleBlockPtyOpened({
            tab_id: (top.tab_id as string) ?? (src.tab_id as string),
            block_run_id:
              (top.block_run_id as string) ??
              (src.block_run_id as string) ??
              (payload.block_id ?? ""),
            block_name: src.block_name as string | undefined,
            title: (top.title as string) ?? (src.title as string | undefined),
            status: src.status as
              | "running"
              | "paused"
              | "done"
              | "error"
              | "cancelled"
              | undefined,
            permission_mode:
              ((top.permission_mode as "safe" | "bypass" | "dangerous" | undefined) ??
                (src.permission_mode as "safe" | "bypass" | "dangerous" | undefined)),
          });
          appendLog({
            timestamp: payload.timestamp,
            level: "info",
            message: `[AI Block] tab opened: ${
              (src.block_name as string) ??
              ((payload as unknown as Record<string, unknown>).title as string) ??
              "AI Block"
            }`,
            workflow_id: payload.workflow_id ?? null,
            block_id: payload.block_id ?? null,
          });
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn("[block_pty_opened] dispatch failed:", err, payload);
        }
        return;
      }
      if (payload.type === "block_pty_closed") {
        try {
          const src = (payload.data ?? {}) as Record<string, unknown>;
          const top = payload as unknown as Record<string, unknown>;
          // Audit P1-D (Codex #866-1): backend emits the outcome under the
          // top-level ``event`` field (one of "completed" |
          // "cancelled_by_user_close" | "error" — see
          // ``ai_pty._internal_notify`` line 654-660). The previous code
          // read ``src.status`` / ``src.result`` from the nested ``data``
          // dict — neither exists on the wire, so every successful run
          // fell through to the conservative "error" default and rendered
          // as a red ✗ in the tab strip.
          const eventField = top.event as
            | "completed"
            | "cancelled_by_user_close"
            | "error"
            | undefined;
          let result: "completed" | "cancelled" | "error" | undefined;
          if (eventField === "completed") {
            result = "completed";
          } else if (eventField === "cancelled_by_user_close") {
            result = "cancelled";
          } else if (eventField === "error") {
            result = "error";
          } else {
            result = (src.result as "completed" | "cancelled" | "error" | undefined);
          }
          handleBlockPtyClosed({
            tab_id: (top.tab_id as string) ?? (src.tab_id as string),
            block_run_id:
              (top.block_run_id as string) ??
              (src.block_run_id as string) ??
              (payload.block_id ?? undefined),
            status: src.status as "done" | "error" | "cancelled" | undefined,
            result,
            detail:
              (top.detail as Record<string, unknown> | undefined) ??
              (src.detail as Record<string, unknown> | undefined),
          });
          // Prefer the top-level ``event`` for the log label so the user
          // sees the actual lifecycle outcome rather than "closed".
          const label =
            (eventField as string | undefined) ??
            (src.status as string) ??
            (src.result as string) ??
            "closed";
          appendLog({
            timestamp: payload.timestamp,
            level: label === "error" ? "error" : "info",
            message: `[AI Block] tab ${label}`,
            workflow_id: payload.workflow_id ?? null,
            block_id: payload.block_id ?? null,
          });
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn("[block_pty_closed] dispatch failed:", err, payload);
        }
        return;
      }

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
