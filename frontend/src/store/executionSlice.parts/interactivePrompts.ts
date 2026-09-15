/**
 * #2395 — interactive prompts, held per `(workflow_id, block_id)`.
 *
 * Several different workflows may run at the same time, and each can pause on
 * an interactive block. A single prompt slot let the later prompt replace the
 * earlier one, leaving the earlier block paused with no window to answer it.
 * Prompts now live in a map keyed by the pair, in arrival order, and answering
 * or cancelling one removes only that entry.
 */
import type { InteractivePrompt } from "../types";

export type InteractivePromptMap = Record<string, InteractivePrompt>;

/** The map key of one paused block of one workflow. */
export function interactivePromptKey(workflowId: string, blockId: string): string {
  return JSON.stringify([workflowId, blockId]);
}

/**
 * Add a prompt, or replace the one already pending for the same block of the
 * same workflow. A replaced entry keeps its place in the arrival order.
 */
export function upsertPrompt(
  prompts: InteractivePromptMap,
  prompt: InteractivePrompt,
): InteractivePromptMap {
  return { ...prompts, [interactivePromptKey(prompt.workflowId, prompt.blockId)]: prompt };
}

/** Remove one workflow's prompt for one block; every other entry is kept. */
export function removePrompt(
  prompts: InteractivePromptMap,
  workflowId: string,
  blockId: string,
): InteractivePromptMap {
  const key = interactivePromptKey(workflowId, blockId);
  if (!(key in prompts)) return prompts;
  const next = { ...prompts };
  delete next[key];
  return next;
}

/**
 * Drop every prompt of a workflow whose run has ended. A block cannot still be
 * waiting for an answer once its workflow emitted `workflow_completed` (the
 * engine emits it for success, failure and cancellation alike).
 */
export function removeWorkflowPrompts(
  prompts: InteractivePromptMap,
  workflowId: string,
): InteractivePromptMap {
  const keys = Object.keys(prompts).filter((key) => prompts[key].workflowId === workflowId);
  if (keys.length === 0) return prompts;
  const next = { ...prompts };
  for (const key of keys) delete next[key];
  return next;
}

/**
 * The one prompt the interactive window shows now.
 *
 * - The prompt already on screen (`shownKey`) stays while it is pending, so a
 *   prompt arriving from another run never swaps the window under the user.
 * - Otherwise the oldest prompt of the workflow on screen wins, so the window
 *   answers for the canvas the user is looking at.
 * - Otherwise the oldest prompt of any workflow is shown, so a paused block
 *   elsewhere is never left without a window.
 *
 * Answering or cancelling the shown prompt surfaces the next one.
 */
export function visibleInteractivePrompt(
  prompts: InteractivePromptMap,
  viewWorkflowId: string | null,
  shownKey: string | null = null,
): InteractivePrompt | null {
  if (shownKey !== null && prompts[shownKey]) return prompts[shownKey];
  const pending = Object.values(prompts);
  if (pending.length === 0) return null;
  return pending.find((prompt) => prompt.workflowId === viewWorkflowId) ?? pending[0];
}
