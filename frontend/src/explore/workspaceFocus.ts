/**
 * ADR-054 spec 5 FR-001, frontend half — telling the agent where the person is.
 *
 * The owner's hard requirement for spec 5 is that the agent always knows
 * whether the person is on the canvas or in an explore session. The channel is
 * the one that already carries the active workflow id — `POST
 * /api/ai/active-context` — extended with an optional `focus` object rather
 * than given a second endpoint, so a frontend and a backend that disagree
 * about focus still agree about the workflow.
 *
 * Spec 5 owns the channel and the backend; this module is the single place the
 * frontend decides what to say and says it. One helper rather than a call at
 * each site: the failure mode issue #2237 tracks is a hand-written fixture
 * agreeing with the frontend while both disagree with the server, and one
 * caller is one thing to assert against the server's model.
 *
 * Three properties of the backend shape the calls here:
 *
 *   1. `mode` is a plain string on the wire, not a closed enum, so a frontend
 *      that learns a mode before the backend does is dropped rather than
 *      answered with a 422. Nothing here defends against that.
 *   2. `workflow_id` is sent in **every** mode. Switching to an Explore tab
 *      does not mean the person closed their workflow, and an agent told
 *      "explore" with no workflow would think they had.
 *   3. Omitting the `focus` key leaves the stored focus untouched; sending
 *      `"focus": null` clears it. So the key is sent only when the focus is
 *      being stated — which is what `postWorkspaceFocus` is for, and why the
 *      pre-existing `postActiveWorkflowContext` (which omits it) still means
 *      "the workflow changed, the focus did not".
 */

import { postWorkspaceFocus, type WorkspaceFocusPayload } from "../lib/api/ai";
import type { AppStore, TabState } from "../store/types";

/**
 * The focus the frontend reports, derived from the active tab.
 *
 * Pure and exported so the wire body can be asserted per mode without a
 * store, a socket, or a fetch in the way.
 */
export function deriveWorkspaceFocus(
  tabs: readonly TabState[],
  activeTabId: string | null,
  workflowId: string | null,
  currentCellId: string | null,
): WorkspaceFocusPayload {
  const active = tabs.find((tab) => tab.id === activeTabId);

  if (active?.kind === "explore" && active.mode === "pause") {
    return {
      mode: "pause",
      workflow_id: workflowId,
      // The paused block and the run it paused in are what the agent needs to
      // say anything useful about a decision the person is being asked for.
      paused_node_id: active.pauseNodeId,
      paused_run_id: active.boundRunId,
      session_path: active.notebookPath,
    };
  }

  if (active?.kind === "explore") {
    return {
      mode: "explore",
      workflow_id: workflowId,
      session_path: active.notebookPath,
      bound_run_id: active.boundRunId,
      current_cell_id: currentCellId,
    };
  }

  // Every other tab kind is the canvas as far as the agent is concerned: a
  // file tab, a preview tab and a workflow tab are all "editing this
  // workflow", and inventing a fourth mode for them would be a vocabulary the
  // backend does not have.
  return { mode: "canvas", workflow_id: workflowId };
}

/** The cell the cursor is in, for the session the active tab shows. */
function currentCellFor(state: AppStore, activeTabId: string | null): string | null {
  const active = state.tabs.find((tab) => tab.id === activeTabId);
  if (active?.kind !== "explore") return null;
  return state.sessions[active.notebookPath]?.currentCell ?? null;
}

/**
 * A stable key for one focus, so the same focus is not reported twice.
 *
 * The subscriber below fires on every store change, and the focus changes far
 * less often than the store does.
 */
export function workspaceFocusKey(focus: WorkspaceFocusPayload): string {
  return JSON.stringify([
    focus.mode,
    focus.workflow_id ?? null,
    focus.session_path ?? null,
    focus.bound_run_id ?? null,
    focus.current_cell_id ?? null,
    focus.paused_node_id ?? null,
    focus.paused_run_id ?? null,
  ]);
}

let lastReportedKey: string | undefined;

/** Forget what was last reported. For tests, and for a project switch. */
export function resetWorkspaceFocusReporter(): void {
  lastReportedKey = undefined;
}

/**
 * Report the focus for this store state, if it changed.
 *
 * Fire-and-forget, like the active-workflow sync it rides beside: a failed
 * report must never block the editor, and the next change re-sends.
 */
export function reportWorkspaceFocus(state: AppStore): void {
  const focus = deriveWorkspaceFocus(
    state.tabs,
    state.activeTabId,
    state.workflowId,
    currentCellFor(state, state.activeTabId),
  );
  const key = workspaceFocusKey(focus);
  if (key === lastReportedKey) return;
  lastReportedKey = key;
  void postWorkspaceFocus(focus).catch((error: unknown) => {
    console.warn("[ai-context] workspace focus sync failed", error);
  });
}
