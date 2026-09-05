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
import { exploreTabIdFor, placeExploreTab } from "../../store/tabSlice.parts/exploreTabActions";
import type { ExploreTab, InteractivePrompt } from "../../store/types";
import { invalidatePanelCatalog } from "../../store/usePanelCatalog";
import { invalidateTypeCatalog } from "../../store/useTypeCatalog";
import { isExploreSessionEvent } from "../../store/exploreSlice";
import type { ExploreSessionEventMessage, LogEntry, WorkflowEventMessage } from "../../types/api";

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
 * ADR-054 spec 4 FR-024 — the tab key of a pause that has no session yet.
 *
 * An Explore tab is keyed by its notebook path, and a paused interactive block
 * has no notebook: FR-026's escalation is what opens one, and until the person
 * asks for it the pause is a tab over one block's decision. The prefix carries
 * a colon so it can never collide with a project-relative notebook path.
 */
export const PAUSE_TAB_PATH_PREFIX = "pause:";

export function pauseTabNotebookPath(blockId: string): string {
  return `${PAUSE_TAB_PATH_PREFIX}${blockId}`;
}

/**
 * FR-024 — put the paused block's Explore tab on screen.
 *
 * This is what replaces `<InteractiveModals />`. The prompt itself still lands
 * in the execution slice, because it carries the descriptor, the payload and
 * the workflow scoping the tab renders and answers from; what changed is where
 * it is drawn, and that a person can now leave it on screen and keep working
 * in another tab, which an overlay covering the Stop control could not allow.
 *
 * Placed rather than opened through `openExploreTab`: that call opens a session
 * first and takes the tab's identity off its response, and a pause has no
 * session until FR-026's escalation makes one.
 */
export function openPauseTab(prompt: InteractivePrompt): ExploreTab {
  const notebookPath = pauseTabNotebookPath(prompt.blockId);
  const tab: ExploreTab = {
    kind: "explore",
    id: exploreTabIdFor(notebookPath),
    notebookPath,
    sessionId: null,
    displayName: prompt.blockType?.trim() ? prompt.blockType.trim() : prompt.blockId,
    mode: "pause",
    boundRunId: null,
    pauseNodeId: prompt.blockId,
    // FR-024 — the notebook pane is absent until the person asks for one.
    notebookVisible: false,
    restoring: false,
    openedAt: Date.now(),
  };
  useAppStore.setState(placeExploreTab(useAppStore.getState(), tab));
  return tab;
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

  /*
   * ADR-054 spec 4 FR-033 — every Explore session event, routed to the one
   * slice that holds session state.
   *
   * First, and by prefix rather than by name: `serialise_session_event` stamps
   * `explore.` on every session event type precisely so the shared hub can
   * tell them apart from engine events, and matching the prefix means a new
   * session event type reaches the slice without a second edit here. The slice
   * ignores a type it does not know, which is the same answer this function
   * would give.
   *
   * The frame carries `session_id` at the top level rather than inside `data`
   * (the engine's frames carry `block_id` / `workflow_id` there instead), so
   * it is re-typed rather than passed through as a `WorkflowEventMessage`.
   *
   * Consumed: these events have no engine consumer, and `consumeEvent` would
   * only add an unhandled type to the execution log.
   */
  if (isExploreSessionEvent(payload.type)) {
    useAppStore
      .getState()
      .applyExploreSessionEvent(payload as unknown as ExploreSessionEventMessage);
    return true;
  }

  if (payload.type === "interactive_prompt") {
    /*
     * ADR-054 spec 4 FR-024 — the prompt opens an Explore tab, not a modal.
     *
     * The prompt still reaches the execution slice unchanged: it carries the
     * panel descriptor the backend resolved, the block's window-sized payload,
     * and the workflow the response must be scoped to, and the pause tab reads
     * all three from there. `InteractiveModals` and its host are deleted; this
     * line is the whole of what replaced them.
     */
    const seen: { prompt: InteractivePrompt | null } = { prompt: null };
    handleInteractivePrompt(payload, {
      setInteractivePrompt: (prompt) => {
        seen.prompt = prompt;
        deps.setInteractivePrompt(prompt);
      },
    });
    if (seen.prompt) openPauseTab(seen.prompt);
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
    // #2113 — the same `refresh_all_registries()` rebuilds the *panel*
    // registry too (#2021), so the Panels tab's listing and choices get
    // the same treatment; without it the tab sat on its first-ever listing.
    invalidatePanelCatalog();
    /*
     * ADR-054 FR-030 — and remount every panel on screen, not just re-read
     * the catalogue. A rebuilt registry is a panel whose document may have
     * been replaced under a mounted frame; re-listing the Panels tab would
     * leave the reader looking at the old rendering of the panel they just
     * changed. This event names no panel, so it bumps the epoch every mount
     * reads rather than one panel's counter.
     */
    useAppStore.getState().notePanelDocumentChanged(null);
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
