/**
 * ADR-054 spec 4 (T-003) — recognising a packaged block, and the two reasons
 * an explore action is offered or refused.
 *
 * Two callers share this: the canvas context menu (FR-002), and the
 * packaged-node double-click (FR-004). S4-A4's notebook badge (FR-030) needs
 * the same answer, which is why the predicate is here rather than inline in
 * either of them.
 *
 * **The gap this was written against is now closed.** `packaging.py` declares
 * `notebook_filename` as a `ClassVar` on the generated block class, and as
 * first written neither `scistudio.api.schemas.BlockSummary` nor
 * `routes/blocks.py::_summary` carried it — so nothing the frontend received
 * said a block had been packaged, this predicate answered `false` for every
 * block, and FR-030's badge and FR-004's double-click were both dead. The
 * agent that found it declared the field here optimistically and said so
 * rather than guessing "packaged" from the origin tier and a sibling file,
 * which would have been a second, disagreeing definition of a packaged block.
 *
 * A no-context audit of the assembled branch found it anyway, which is the
 * point of running one: the frontend agreed with itself, the backend agreed
 * with itself, and only reading both against each other showed the field had
 * no writer. The manager landed the backend half — `notebook_filename` on
 * `BlockSummary`, normalised from the block's ClassVar with empty becoming
 * `None` — so the truthiness test below is now answered by real data.
 */

import type { BlockSummary, WorkflowNode } from "../types/api";

/** Why the explore action is disabled, in the words the menu shows. */
export const NOTHING_TO_EXPLORE_REASON = "This block has not produced any outputs yet.";

/**
 * FR-002 — whether a block node's outputs exist.
 *
 * "The runtime reports no outputs" is the whole test: `blockOutputs` is
 * written from the engine's `block_done` events, so a node absent from it, or
 * present with an empty payload, has produced nothing in this session. Nothing
 * here inspects the block's schema — a block that *declares* outputs but has
 * not run has nothing to explore, which is exactly the case the disabled
 * action is for.
 */
export function hasExploreableOutputs(
  nodeId: string,
  blockOutputs: Record<string, Record<string, unknown>> | undefined,
): boolean {
  const outputs = blockOutputs?.[nodeId];
  if (!outputs) return false;
  return Object.keys(outputs).length > 0;
}

/**
 * FR-004 / FR-030 — whether this block is one packaged from a notebook.
 *
 * Reads the marker the backend does not send yet (see the module docstring).
 * Written as one predicate so the double-click, the badge, and any later
 * consumer cannot drift apart.
 */
export function isPackagedNotebookBlock(summary: BlockSummary | undefined): boolean {
  return Boolean(summary?.notebook_filename);
}

/** The block name a packaged node's session is reopened by. */
export function packagedBlockNameFor(
  node: WorkflowNode | undefined,
  summary: BlockSummary | undefined,
): string | null {
  if (!isPackagedNotebookBlock(summary)) return null;
  return summary?.type_name ?? node?.block_type ?? null;
}
