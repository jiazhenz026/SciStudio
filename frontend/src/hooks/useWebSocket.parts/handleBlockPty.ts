/**
 * ADR-035 §3.10 dispatch handlers for ``block_pty_opened`` /
 * ``block_pty_closed`` events. Extracted from ``useWebSocket`` in #1413
 * / #1414.
 */
import {
  handleBlockPtyClosed as dispatchBlockPtyClosed,
  handleBlockPtyOpened as dispatchBlockPtyOpened,
} from "../../components/AIChat/blockPtyHandlers";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

export interface BlockPtyDeps {
  appendLog: (entry: LogEntry) => void;
}

type PtyResult = "completed" | "cancelled" | "error" | undefined;

function resolvePtyResult(eventField: string | undefined, srcResult: unknown): PtyResult {
  if (eventField === "completed") return "completed";
  if (eventField === "cancelled_by_user_close") return "cancelled";
  if (eventField === "error") return "error";
  return srcResult as PtyResult;
}

export function handleBlockPtyOpened(payload: WorkflowEventMessage, deps: BlockPtyDeps): void {
  try {
    // The wire payload may live at the top level OR nested under `data`,
    // depending on which engine path emitted it. Tolerate both.
    const src = (payload.data ?? {}) as Record<string, unknown>;
    const top = payload as unknown as Record<string, unknown>;
    // Audit P2-A (Codex #866-2): backend emits ``permission_mode`` at the
    // top level. Mirror the resilience pattern used for tab_id / block_run_id.
    dispatchBlockPtyOpened({
      tab_id: (top.tab_id as string) ?? (src.tab_id as string),
      block_run_id:
        (top.block_run_id as string) ?? (src.block_run_id as string) ?? payload.block_id ?? "",
      block_name: src.block_name as string | undefined,
      title: (top.title as string) ?? (src.title as string | undefined),
      status: src.status as "running" | "paused" | "done" | "error" | "cancelled" | undefined,
      permission_mode:
        (top.permission_mode as "safe" | "bypass" | "dangerous" | undefined) ??
        (src.permission_mode as "safe" | "bypass" | "dangerous" | undefined),
    });
    deps.appendLog({
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
    console.warn("[block_pty_opened] dispatch failed:", err, payload);
  }
}

export function handleBlockPtyClosed(payload: WorkflowEventMessage, deps: BlockPtyDeps): void {
  try {
    const src = (payload.data ?? {}) as Record<string, unknown>;
    const top = payload as unknown as Record<string, unknown>;
    // Audit P1-D (Codex #866-1): backend emits the outcome under the top-
    // level ``event`` field. Mirror that here.
    const eventField = top.event as "completed" | "cancelled_by_user_close" | "error" | undefined;
    const result = resolvePtyResult(eventField, src.result);
    dispatchBlockPtyClosed({
      tab_id: (top.tab_id as string) ?? (src.tab_id as string),
      block_run_id:
        (top.block_run_id as string) ??
        (src.block_run_id as string) ??
        payload.block_id ??
        undefined,
      status: src.status as "done" | "error" | "cancelled" | undefined,
      result,
      detail:
        (top.detail as Record<string, unknown> | undefined) ??
        (src.detail as Record<string, unknown> | undefined),
    });
    const label =
      (eventField as string | undefined) ??
      (src.status as string) ??
      (src.result as string) ??
      "closed";
    deps.appendLog({
      timestamp: payload.timestamp,
      level: label === "error" ? "error" : "info",
      message: `[AI Block] tab ${label}`,
      workflow_id: payload.workflow_id ?? null,
      block_id: payload.block_id ?? null,
    });
  } catch (err) {
    console.warn("[block_pty_closed] dispatch failed:", err, payload);
  }
}
