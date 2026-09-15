/**
 * ADR-040 Addendum 5 / #1488 — publish the editor's active workflow so the
 * chat agent's `get_active_workflow_context` MCP tool reflects what the GUI
 * shows.
 *
 * #2395 — a page publishes only on a real transition of what it shows:
 *
 * - The identity is `(project, workflow)`. A workflow id repeats across
 *   projects (every new project starts on `main`), so deduping on the id alone
 *   sent nothing when the user moved to another project's `main`.
 * - The page's starting value counts as already in sync. A freshly loaded page
 *   has no workflow, and announcing that `null` from store initialisation
 *   cleared the context the user's own window (or the backend's persisted
 *   value) holds.
 * - A move between two "no workflow" states (the intermediate steps of
 *   switching projects) publishes nothing: `null` is `null` in any project.
 * - A page attached through an `open_gui` deep link (#2385) never publishes;
 *   it watches the user's session and must not overwrite it.
 */

export interface ActiveWorkflowContext {
  projectId: string | null;
  workflowId: string | null;
}

export interface ActiveWorkflowSyncDeps {
  post: (workflowId: string | null) => Promise<unknown>;
  isAttached: () => boolean;
}

/** Return a sync function seeded with the page's starting context. */
export function createActiveWorkflowSync(
  initial: ActiveWorkflowContext,
  { post, isAttached }: ActiveWorkflowSyncDeps,
): (next: ActiveWorkflowContext) => void {
  let last = initial;
  return (next) => {
    if (isAttached()) return;
    if (next.projectId === last.projectId && next.workflowId === last.workflowId) return;
    const previous = last;
    last = next;
    if (next.workflowId === null && previous.workflowId === null) return;
    void post(next.workflowId).catch((err) => {
      // Best-effort: a failed sync MUST NOT block the editor. The chat agent
      // simply won't see the latest id this turn; the next change re-emits.
      console.warn("[ai-context] active workflow sync failed", err);
    });
  };
}
