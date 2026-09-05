/**
 * ADR-054 spec 4 (T-012, T-015) — what the block palette needs from an Explore
 * session (FR-029, FR-031).
 *
 * Two things, kept out of `BlockPalette.tsx` so the palette keeps reading as a
 * palette:
 *
 *   1. `packagedSignature` — a stable key over every session's last
 *      `explore.packaged` payload, so the palette can refresh exactly when the
 *      runtime says a block was packaged and not on every unrelated store
 *      change (FR-029).
 *   2. `blockCallSource` and `activeExploreTarget` — the cell text a card's
 *      insert-call action writes, and whether there is an Explore session to
 *      write it into (FR-031).
 *
 * The call text is a *template*, not runtime truth: it is the syntax
 * `scistudio.explore.block_call` documents — `blocks.run("<identifier>",
 * <port>=<value>)` — with `...` where the person supplies a value. Ellipsis
 * rather than a blank because the cell must parse: the dependency analysis
 * reads every cell with `ast.parse`, and an unparsable cell would be flagged
 * for a template the person had not finished typing.
 *
 * TODO(#2253): every port is written `...` rather than filled from the live
 *   bindings, and a port whose name is not a Python identifier is omitted.
 *   Out of scope per the ADR-054 assembly dispatch: T-015 is the insert, and
 *   reading the bindings response into the palette is a wider change than the
 *   card's action.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `F-A4-006`.
 */

import type { AppStore } from "../../store/types";
import type { BlockSummary } from "../../types/api";

/** Python's identifier shape, near enough for a template. */
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** The session a card's insert-call action would write into. */
export interface ExploreCallTarget {
  sessionId: string;
  notebookPath: string;
  /** The cell the new one goes after; `null` inserts at the end. */
  currentCell: string | null;
}

/**
 * The active Explore tab's session, or `null` when no Explore tab is active.
 *
 * `null` is what keeps FR-031's other half true: with no Explore tab up, the
 * card renders exactly what it rendered before this change.
 */
export function activeExploreTarget(state: AppStore): ExploreCallTarget | null {
  const active = state.tabs.find((tab) => tab.id === state.activeTabId);
  if (active?.kind !== "explore") return null;
  const session = state.sessions[active.notebookPath];
  // A session that has not opened yet has no id to send the insert to, and a
  // failed one has nothing to insert into.
  if (!session || session.shellState !== "ready" || !session.sessionId) return null;
  return {
    sessionId: session.sessionId,
    notebookPath: session.notebookPath,
    currentCell: session.currentCell,
  };
}

/**
 * The two primitive selectors the action subscribes through.
 *
 * `activeExploreTarget` builds a fresh object every call, and zustand v5
 * compares a selector's result by identity — subscribing to it directly would
 * re-render the card on every store change and warn about an uncached
 * snapshot. Selecting the two strings separately subscribes to what actually
 * matters and nothing else.
 */
export function activeExploreSessionId(state: AppStore): string | null {
  return activeExploreTarget(state)?.sessionId ?? null;
}

export function activeExploreCurrentCell(state: AppStore): string | null {
  return activeExploreTarget(state)?.currentCell ?? null;
}

/** Turn a port name into something that can stand on the left of an `=`. */
function toIdentifier(raw: string, fallback: string): string {
  const cleaned = raw.replace(/[^A-Za-z0-9_]/g, "_").replace(/^(?=\d)/, "_");
  return IDENTIFIER.test(cleaned) ? cleaned : fallback;
}

/**
 * The name the call's result binds to.
 *
 * `BlockCallAdapter.call` returns the single output port's value when a block
 * declares exactly one, and a mapping of port name to value otherwise — so a
 * one-output block names its result after that port and anything else binds
 * `result`.
 */
export function callTargetName(block: BlockSummary): string {
  const outputs = block.output_ports ?? [];
  if (outputs.length === 1) return toIdentifier(outputs[0].name, "result");
  return "result";
}

/**
 * The cell text for a call to `block`.
 *
 * Every input port appears as a keyword argument, because the keywords are how
 * the adapter splits ports from configuration; a port whose name is not a
 * Python identifier cannot be passed as one at all and is left out rather than
 * written as something that would not run.
 */
export function blockCallSource(block: BlockSummary): string {
  const target = callTargetName(block);
  const args = (block.input_ports ?? [])
    .filter((port) => IDENTIFIER.test(port.name))
    .map((port) => `${port.name}=...`);
  const parts = [JSON.stringify(block.type_name), ...args];
  return `${target} = blocks.run(${parts.join(", ")})`;
}

/**
 * A key over every session's last packaged payload.
 *
 * Changes exactly when a session records a new `explore.packaged`, which is
 * what FR-029's refresh must key on: the palette re-fetches because the
 * runtime said a block was written, never because a cell ran.
 */
export function packagedSignature(sessions: AppStore["sessions"]): string {
  const parts: string[] = [];
  for (const path of Object.keys(sessions).sort()) {
    const packaged = sessions[path]?.lastPackaged;
    if (!packaged) continue;
    parts.push(`${path}|${packaged.block_name}|${packaged.notebook_commit}`);
  }
  return parts.join("\n");
}
