/**
 * ADR-054 spec 4 (T-003) — recognising a packaged block, and the two reasons
 * an explore action is offered or refused.
 *
 * Two callers share this: the canvas context menu (FR-002), and the
 * packaged-node double-click (FR-004). S4-A4's notebook badge (FR-030) needs
 * the same answer, which is why the predicate is here rather than inline in
 * either of them.
 *
 * **A known gap.** `packaging.py` writes `notebook_filename` and
 * `notebook_commit` as `ClassVar`s on the generated block class, but
 * `scistudio.api.schemas.BlockSummary` does not carry either, and
 * `routes/blocks.py::_summary` does not read them — so as the backend stands,
 * nothing the frontend receives says a block was packaged from a notebook.
 * `notebook_filename` is declared optional on the frontend's `BlockSummary`
 * against the backend change that surfaces it; until that lands the predicate
 * answers `false` for every block, the double-click keeps its pre-ADR-054
 * behaviour, and no request is sent speculatively. Recorded as a finding
 * rather than worked around, because guessing at "packaged" from the block's
 * origin tier and a sibling file would be a second, disagreeing definition of
 * what a packaged block is.
 *
 * TODO(#2253): the packaged-notebook marker is not on the wire.
 *   Out of scope per the ADR-054 assembly dispatch — the backend surface is
 *   spec 3's, and no agent in this dispatch may write `src/scistudio/**`.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `## S4-A1`.
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
