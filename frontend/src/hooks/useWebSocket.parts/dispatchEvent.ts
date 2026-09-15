/**
 * Message dispatcher for ``useWebSocket``. Routes incoming
 * ``WorkflowEventMessage`` payloads to the appropriate extracted
 * handler. Extracted from ``useWebSocket`` in #1413 / #1414.
 *
 * Returning ``true`` from a handler call indicates the message was
 * fully consumed; the caller MUST NOT also forward it to
 * ``consumeEvent``. The ``workflow_started`` branch returns ``false``
 * because the executionSlice still needs the event to flip the
 * workflow's running flag.
 */
import { receivePanelDecision } from "../../panels/decisions";
import type { VersionedWorkflowResponse } from "../../lib/api";
import { useAppStore } from "../../store";
import { TUTORIAL_SYNC_EVENT_TYPES } from "../../store/learningCenterSlice";
import type { InteractivePrompt } from "../../store/types";
import { invalidatePreviewerCatalog } from "../../store/usePreviewerCatalog";
import { invalidateTypeCatalog } from "../../store/useTypeCatalog";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

import { handleBlockPtyClosed, handleBlockPtyOpened } from "./handleBlockPty";
import { handleFileChanged } from "./handleFileChanged";
import {
  handleGitHeadChanged,
  handleInteractivePrompt,
  handleWorkflowStartedAutoOpen,
} from "./handleLifecycle";
import { handleOpenMiniApp, handlePanelFilesChanged, handleWsHello } from "./handleMiniApp";
import { handleWorkflowChanged } from "./handleWorkflowChanged";

export interface DispatchDeps {
  appendLog: (entry: LogEntry) => void;
  upsertInteractivePrompt: (prompt: InteractivePrompt) => void;
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
  /*
   * ADR-054 MiniApps (#2354), CONTRACT §2.1 — the first frame on the socket.
   *
   * Before everything else because it is not a workflow event at all: it
   * carries no block, no workflow and no event data, and it is the identity
   * every later MiniApp context create is bound to. The matching clear lives
   * in `handleWsDisconnected`, which the socket hook calls when the connection
   * drops — a client id the backend has retired must not outlive its socket.
   */
  if (payload.type === "hello") {
    handleWsHello(payload, { setWsClientId: useAppStore.getState().setWsClientId });
    return true;
  }

  if (TUTORIAL_SYNC_EVENT_TYPES.has(payload.type)) {
    void useAppStore.getState().syncActiveTutorialSession();
  }

  if (receivePanelDecision(payload)) return true;

  if (payload.type === "interactive_prompt") {
    handleInteractivePrompt(payload, { upsertInteractivePrompt: deps.upsertInteractivePrompt });
    return true;
  }
  if (payload.type === "workflow_started") {
    handleWorkflowStartedAutoOpen(payload);
    // Fall through so executionSlice still gets the event for the workflow's running flag.
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
    // #2113 — the same `refresh_all_registries()` rebuilds the *previewer*
    // registry too (#2021), so the Previewers tab's listing and choices get
    // the same treatment; without it the tab sat on its first-ever listing.
    invalidatePreviewerCatalog();
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
  if (payload.type === "panel.open_miniapp") {
    // ADR-054 FR-030: the agent asked the workspace to open a MiniApp on one
    // output. Consumed here — nothing downstream reads it, unlike
    // `workflow_started` above, whose branch returns false on purpose.
    handleOpenMiniApp(payload, {
      openMiniAppTab: useAppStore.getState().openMiniAppTab,
      appendLog: deps.appendLog,
    });
    return true;
  }
  if (payload.type === "panel.files_changed") {
    // ADR-054 FR-022: the panel directory of an open MiniApp changed on disk.
    // The 500 ms debounce lives in the handler, not in the tab: this is where
    // the burst arrives, and one reload per burst is cheaper than one per tab.
    handlePanelFilesChanged(payload, {
      notifyPanelFilesChanged: useAppStore.getState().notifyPanelFilesChanged,
    });
    return true;
  }
  return false;
}
