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
}

interface ActiveContextResponse {
  workflow_id: string | null;
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
  return apiFetch<ActiveContextResponse>("/api/ai/active-context", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ workflow_id: workflowId } satisfies ActiveContextPayload),
  });
}
