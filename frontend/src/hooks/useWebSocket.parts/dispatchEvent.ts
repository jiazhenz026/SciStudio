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
import { useAppStore } from "../../store";
import { TUTORIAL_SYNC_EVENT_TYPES } from "../../store/learningCenterSlice";
import type { InteractivePrompt } from "../../store/types";
import { invalidateTypeCatalog } from "../../store/useTypeCatalog";
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
  setInteractivePrompt: (prompt: InteractivePrompt | null) => void;
  setWorkflow: (workflow: VersionedWorkflowResponse | null) => void;
}

/**
 * @returns ``true`` when the event was fully consumed by a specialized
 *   handler; ``false`` when the caller should also forward it to
 *   ``consumeEvent`` (workflow lifecycle / unknown types).
 */
export function dispatchWorkflowEvent(payload: WorkflowEventMessage, deps: DispatchDeps): boolean {
  /*
   * ADR-053 Learning Center (#2057) — a running tutorial re-checks its step
   * whenever one of FR-050's events lands.
   *
   * Before the branches below, not inside one: the events that matter are
   * split across them, and `block_done` / `workflow_completed` are not handled
   * here at all — they return `false` and fall through to `consumeEvent`. This
   * is also a notification rather than a handler, so it does not consume the
   * event; every existing consumer still sees it. The call returns immediately
   * when no tutorial is running.
   */
  if (TUTORIAL_SYNC_EVENT_TYPES.has(payload.type)) {
    void useAppStore.getState().syncActiveTutorialSession();
  }

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
  if (payload.type === "blocks.reloaded") {
    // #9: the block registry was hot-reloaded (e.g. the agent scaffolded +
    // reloaded a custom block). Signal App to re-fetch the block catalog so the
    // palette and canvas nodes pick up the new/changed block without a manual
    // palette reload.
    useAppStore.getState().bumpBlockCatalogRefresh();
    // ADR-053 FR-062: every emitter of this event reaches it through
    // `refresh_all_registries()`, which rebuilds the *type* registry too — a
    // palette reload, a project file save, a package install, an agent
    // promotion. Bumping only the block counter left the Data types tab and
    // the declared canvas colours on their first-ever listing until the user
    // pressed Reload by hand.
    invalidateTypeCatalog();
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
