/**
 * Message dispatcher for ``useWebSocket``. Routes incoming
 * ``WorkflowEventMessage`` payloads to the appropriate extracted
 * handler. Extracted from ``useWebSocket`` in #1413 / #1414.
 *
 * Returning ``true`` from a handler call indicates the message was
 * fully consumed; the caller MUST NOT also forward it to
 * ``consumeEvent``. The ``workflow_started`` branch returns ``false``
 * because the executionSlice still needs the event to flip
 * ``isRunning``.
 */
import type { VersionedWorkflowResponse } from "../../lib/api";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

import { handleBlockPtyClosed, handleBlockPtyOpened } from "./handleBlockPty";
import { handleFileChanged } from "./handleFileChanged";
import {
  handleGitHeadChanged,
  handleInteractivePrompt,
  handleWorkflowStartedAutoOpen,
} from "./handleLifecycle";
import { handleWorkflowChanged } from "./handleWorkflowChanged";

export interface DispatchDeps {
  appendLog: (entry: LogEntry) => void;
  setInteractivePrompt: (
    prompt: { blockId: string; blockType: string; data: Record<string, unknown> } | null,
  ) => void;
  setWorkflow: (workflow: VersionedWorkflowResponse | null) => void;
}

/**
 * @returns ``true`` when the event was fully consumed by a specialized
 *   handler; ``false`` when the caller should also forward it to
 *   ``consumeEvent`` (workflow lifecycle / unknown types).
 */
export function dispatchWorkflowEvent(payload: WorkflowEventMessage, deps: DispatchDeps): boolean {
  if (payload.type === "interactive_prompt") {
    handleInteractivePrompt(payload, { setInteractivePrompt: deps.setInteractivePrompt });
    return true;
  }
  if (payload.type === "workflow_started") {
    handleWorkflowStartedAutoOpen(payload);
    // Fall through so executionSlice still gets the event for isRunning.
    return false;
  }
  if (payload.type === "workflow.changed") {
    handleWorkflowChanged(payload, {
      appendLog: deps.appendLog,
      setWorkflow: deps.setWorkflow,
    });
    return true;
  }
  if (payload.type === "file.changed") {
    handleFileChanged(payload, { appendLog: deps.appendLog });
    return true;
  }
  if (payload.type === "git.head_changed") {
    handleGitHeadChanged(payload);
    return true;
  }
  if (payload.type === "block_pty_opened") {
    handleBlockPtyOpened(payload, { appendLog: deps.appendLog });
    return true;
  }
  if (payload.type === "block_pty_closed") {
    handleBlockPtyClosed(payload, { appendLog: deps.appendLog });
    return true;
  }
  return false;
}
