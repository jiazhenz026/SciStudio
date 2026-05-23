/**
 * Pure helpers for ``executionSlice.consumeEvent``. Extracted in #1414
 * to drop the cyclomatic complexity below the 15 cap. The legacy reducer
 * mixed five concerns (state transitions, output extraction, workflow
 * lifecycle, error capture, log appending) into one arrow — these
 * helpers split each concern so the slice can compose them.
 */
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

type ExecutionEvent = WorkflowEventMessage;

export interface BlockErrorExtraction {
  isBlockError: boolean;
  errorText: string | undefined;
  summaryText: string | undefined;
}

/** Detect a block_error event and pull out the error/summary strings. */
export function extractBlockError(event: ExecutionEvent): BlockErrorExtraction {
  const isBlockError =
    event.type === "block_error" && event.block_id !== null && event.block_id !== undefined;
  if (!isBlockError) {
    return { isBlockError: false, errorText: undefined, summaryText: undefined };
  }
  const errorText = typeof event.data.error === "string" ? event.data.error : undefined;
  const summaryText =
    typeof event.data.error_summary === "string" ? event.data.error_summary : undefined;
  return { isBlockError, errorText, summaryText };
}

/**
 * Compute the next ``isRunning`` flag from a workflow-lifecycle event.
 * Returns ``current`` unchanged when the event is not a lifecycle event.
 */
export function nextIsRunning(event: ExecutionEvent, current: boolean): boolean {
  if (event.type === "workflow_started") return true;
  if (event.type === "workflow_completed") return false;
  return current;
}

/** Merge a block-state transition into the existing per-block map. */
export function nextBlockStates(
  event: ExecutionEvent,
  current: Record<string, string>,
): Record<string, string> {
  if (!event.block_id) return current;
  return {
    ...current,
    [event.block_id]: event.type.replace("block_", ""),
  };
}

/** Merge an outputs payload into the existing per-block outputs map. */
export function nextBlockOutputs(
  event: ExecutionEvent,
  current: Record<string, Record<string, unknown>>,
): Record<string, Record<string, unknown>> {
  if (!event.block_id || !event.data.outputs || typeof event.data.outputs !== "object") {
    return current;
  }
  return {
    ...current,
    [event.block_id]: event.data.outputs as Record<string, unknown>,
  };
}

/**
 * Build the per-block error/summary maps from a block_error event. Pass
 * through the existing maps when the event is not a block_error.
 */
export function nextErrorMaps(
  event: ExecutionEvent,
  extraction: BlockErrorExtraction,
  currentErrors: Record<string, string>,
  currentSummaries: Record<string, string>,
): { nextErrors: Record<string, string>; nextSummaries: Record<string, string> } {
  const { isBlockError, errorText, summaryText } = extraction;
  if (!isBlockError || !event.block_id) {
    return { nextErrors: currentErrors, nextSummaries: currentSummaries };
  }
  const nextErrors =
    errorText !== undefined ? { ...currentErrors, [event.block_id]: errorText } : currentErrors;
  const nextSummaries =
    summaryText !== undefined
      ? { ...currentSummaries, [event.block_id]: summaryText }
      : currentSummaries;
  return { nextErrors, nextSummaries };
}

/**
 * Optionally append a structured log entry for the block_error so the
 * Logs panel can render it alongside the standard log stream.
 */
export function maybeAppendErrorLog(
  event: ExecutionEvent,
  extraction: BlockErrorExtraction,
  current: LogEntry[],
): { logEntries: LogEntry[]; appended: boolean } {
  const { isBlockError, errorText } = extraction;
  if (!isBlockError || errorText === undefined) {
    return { logEntries: current, appended: false };
  }
  const next: LogEntry = {
    timestamp: event.timestamp,
    level: "error",
    message: errorText,
    workflow_id: event.workflow_id ?? null,
    block_id: event.block_id ?? null,
  };
  return { logEntries: [...current, next].slice(-400), appended: true };
}
