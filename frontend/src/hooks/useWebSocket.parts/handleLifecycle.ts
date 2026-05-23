/**
 * Lifecycle/auxiliary event handlers (``interactive_prompt``,
 * ``workflow_started`` auto-open, ``git.head_changed``) extracted from
 * ``useWebSocket`` in #1413 / #1414.
 */
import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import type { WorkflowEventMessage } from "../../types/api";

export interface LifecycleDeps {
  setInteractivePrompt: (
    prompt: { blockId: string; blockType: string; data: Record<string, unknown> } | null,
  ) => void;
}

export function handleInteractivePrompt(payload: WorkflowEventMessage, deps: LifecycleDeps): void {
  // #591/#594: surface backend interactive_prompt events.
  deps.setInteractivePrompt({
    blockId: payload.block_id ?? "",
    blockType: (payload.data.block_type as string) ?? "",
    data: payload.data,
  });
}

export function handleWorkflowStartedAutoOpen(payload: WorkflowEventMessage): void {
  // When an agent kicks off a run via the MCP ``run_workflow`` tool, the
  // scheduler emits ``workflow_started`` for the existing YAML — no
  // ``workflow.changed`` event fires. Mirror the workflow.changed
  // ``kind=created`` auto-open path so the user can watch progress.
  const startedId = (payload.workflow_id as string | null | undefined) ?? null;
  if (!startedId) return;
  if (
    useAppStore.getState().tabs.some((t) => t.kind === "workflow" && t.workflowId === startedId)
  ) {
    return;
  }
  // Defensive: ``api.getWorkflow`` may be vi.mocked and return
  // undefined when this hook runs in unrelated unit tests.
  const fetchPromise = api.getWorkflow(startedId);
  if (!fetchPromise || typeof fetchPromise.then !== "function") return;
  fetchPromise
    .then((fresh) => {
      const tabs = useAppStore.getState().tabs;
      if (!tabs.some((t) => t.kind === "workflow" && t.workflowId === startedId)) {
        useAppStore.getState().openTab(fresh, startedId);
      }
    })
    .catch(() => {
      // best-effort; user can still open it via the file tree
    });
}

export function handleGitHeadChanged(payload: WorkflowEventMessage): void {
  // ADR-039 §3.8: HEAD or branch-tip moved on disk. The Git tab and
  // canvas must invalidate cached log / branch / status views.
  const data = (payload.data ?? {}) as Record<string, unknown>;
  const commitSha = (data.commit_sha as string | null | undefined) ?? null;
  const ref = (data.ref as string | undefined) ?? "HEAD";
  const kind = (data.kind as string | undefined) ?? "head";
  try {
    useAppStore.getState().invalidateHistory();
  } catch (err) {
    console.warn("[git.head_changed] invalidateHistory failed", err);
  }
  // eslint-disable-next-line no-console
  console.debug(
    "[git.head_changed] commit=%s ref=%s kind=%s (gitSlice invalidated)",
    commitSha,
    ref,
    kind,
  );
}
