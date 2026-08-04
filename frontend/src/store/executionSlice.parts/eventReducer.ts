/**
 * Pure helpers for ``executionSlice.consumeEvent``. Extracted in #1414
 * to drop the cyclomatic complexity below the 15 cap. The legacy reducer
 * mixed five concerns (state transitions, output extraction, workflow
 * lifecycle, error capture, log appending) into one arrow — these
 * helpers split each concern so the slice can compose them.
 */
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

type ExecutionEvent = WorkflowEventMessage;
const MAX_ERROR_SUMMARY_LEN = 160;
const PYTHON_EXCEPTION_PREFIX = /^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning):\s*/;

export interface BlockErrorExtraction {
  isBlockError: boolean;
  errorText: string | undefined;
  summaryText: string | undefined;
}

export function summarizeErrorText(errorText: string | undefined): string | undefined {
  if (errorText === undefined) return undefined;
  const lines = errorText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const lastLine = lines[lines.length - 1] ?? errorText.trim();
  const cleaned = lastLine.replace(PYTHON_EXCEPTION_PREFIX, "").replace(/\s+/g, " ").trim();
  const summary = cleaned || "Block failed.";
  return summary.length > MAX_ERROR_SUMMARY_LEN
    ? `${summary.slice(0, MAX_ERROR_SUMMARY_LEN - 1)}…`
    : summary;
}

/** Detect a block_error event and pull out the error/summary strings. */
export function extractBlockError(event: ExecutionEvent): BlockErrorExtraction {
  const isBlockError =
    event.type === "block_error" && event.block_id !== null && event.block_id !== undefined;
  if (!isBlockError) {
    return { isBlockError: false, errorText: undefined, summaryText: undefined };
  }
  const errorText = typeof event.data.error === "string" ? event.data.error : undefined;
  const rawSummary =
    typeof event.data.error_summary === "string" ? event.data.error_summary : errorText;
  const summaryText = summarizeErrorText(rawSummary);
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

/**
 * Resolve the instant a block entered the running state (#1974).
 *
 * The engine stamps every event with its own clock (`EngineEvent.timestamp`,
 * serialised by `api/ws.py`), so the backend stays the source of runtime truth
 * and the node's elapsed counter is anchored to when the block ACTUALLY
 * started, not to when this client happened to render the transition.
 *
 * Falls back to the client's receive time when the payload carries no parsable
 * timestamp, or when the engine clock reads ahead of this client's (a remote
 * engine with skewed clocks would otherwise produce a negative elapsed time).
 */
export function resolveRunStartedAt(rawTimestamp: string | undefined, now: number): number {
  if (!rawTimestamp) return now;
  const parsed = Date.parse(rawTimestamp);
  if (Number.isNaN(parsed) || parsed > now) return now;
  return parsed;
}

/**
 * Track the start instant of the CURRENT run of each block (#1974).
 *
 * The map holds an entry only while a block is running: `block_running` stamps
 * it, and any later event for that block (done / error / cancelled / skipped /
 * paused / ready / interactive prompt) drops it. That keeps the entry in
 * lockstep with `nextBlockStates` — an entry exists exactly while the node's
 * status surface shows the running spinner — so no final duration and no run
 * history survive on the node.
 */
export function nextBlockRunStarts(
  event: ExecutionEvent,
  current: Record<string, number>,
  now: number = Date.now(),
): Record<string, number> {
  if (!event.block_id) return current;
  if (event.type === "block_running") {
    return { ...current, [event.block_id]: resolveRunStartedAt(event.timestamp, now) };
  }
  if (!(event.block_id in current)) return current;
  const next = { ...current };
  delete next[event.block_id];
  return next;
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
  const { isBlockError, errorText, summaryText } = extraction;
  if (!isBlockError || (errorText === undefined && summaryText === undefined)) {
    return { logEntries: current, appended: false };
  }
  const next: LogEntry = {
    timestamp: event.timestamp,
    level: "error",
    message: summaryText ?? errorText ?? "Block failed.",
    details: errorText !== undefined && errorText !== summaryText ? errorText : undefined,
    workflow_id: event.workflow_id ?? null,
    block_id: event.block_id ?? null,
  };
  return { logEntries: [...current, next].slice(-400), appended: true };
}
