/**
 * AI agent endpoints — ADR-040 Addendum 5 / #1488.
 *
 * Surfaces the active workflow id from the GUI to the backend so the
 * chat agent's ``get_active_workflow_context`` MCP tool can report
 * what the user is currently editing. The store-level subscriber in
 * ``frontend/src/store/index.ts`` POSTs through here on every
 * ``workflowId`` transition.
 */

import { apiFetch, JSON_HEADERS } from "./core";

interface ActiveContextPayload {
  workflow_id: string | null;
  focus?: WorkspaceFocusPayload | null;
}

interface ActiveContextResponse {
  workflow_id: string | null;
}

/**
 * ADR-054 spec 5 FR-001 - where the person is, on the channel that already
 * carries what they are editing.
 *
 * `mode` is the only required field. It is typed here as the three modes the
 * frontend can be in, but it travels as a plain string: the backend types it
 * `str` rather than a `Literal` so a frontend that learns a mode before the
 * backend does is dropped rather than answered with a 422.
 *
 * The rest are per mode - `session_path` and `bound_run_id` for an explore
 * session, `paused_node_id` and `paused_run_id` for a pause - and
 * `workflow_id` is sent in every mode, because switching to an Explore tab
 * does not mean the person closed their workflow.
 */
export interface WorkspaceFocusPayload {
  mode: "canvas" | "explore" | "pause";
  workflow_id?: string | null;
  /** Project-relative notebook path of the session on screen. */
  session_path?: string | null;
  bound_run_id?: string | null;
  current_cell_id?: string | null;
  paused_node_id?: string | null;
  paused_run_id?: string | null;
}

/**
 * Tell the backend which workflow the editor is currently showing.
 *
 * Pass ``null`` when no workflow is open (e.g. the user closed the
 * editor or switched projects). The backend persists the value to
 * ``<project>/.scistudio/active_workflow.json`` so it survives backend
 * restart; the MCP tool reads back from the runtime field.
 *
 * Fire-and-forget on the caller side — failures are swallowed and
 * logged because a failed sync MUST NOT block the editor flow.
 */
export async function postActiveWorkflowContext(
  workflowId: string | null,
): Promise<ActiveContextResponse> {
  // The `focus` key is deliberately absent, not null: the backend tells the
  // two apart through `model_fields_set`, and omitting it means "the workflow
  // changed, the focus did not" rather than "the person is nowhere".
  return apiFetch<ActiveContextResponse>("/api/ai/active-context", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ workflow_id: workflowId } satisfies ActiveContextPayload),
  });
}

/**
 * ADR-054 spec 5 FR-001 - tell the backend where the person is.
 *
 * Sends the focus **and** the workflow id, on the one channel, so an agent
 * that reads the context tool is never told a mode without the workflow
 * behind it. Pass `null` to clear the stored focus; omit the call entirely to
 * leave it alone.
 *
 * Fire-and-forget on the caller side, like `postActiveWorkflowContext`.
 */
export async function postWorkspaceFocus(
  focus: WorkspaceFocusPayload | null,
): Promise<ActiveContextResponse> {
  return apiFetch<ActiveContextResponse>("/api/ai/active-context", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      workflow_id: focus?.workflow_id ?? null,
      focus,
    } satisfies ActiveContextPayload),
  });
}
