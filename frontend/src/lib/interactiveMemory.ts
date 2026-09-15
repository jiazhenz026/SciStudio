/**
 * ADR-051 interaction memory (Addendum 1): a remembered interactive decision so
 * future runs skip the dialog and compute directly.
 *
 * The record lives in the node config (the frontend owns the workflow
 * definition; the engine only reads it). It is generic — it carries the whole
 * decision verbatim plus the input fingerprint that gates replay — so every
 * interactive block, core or package, inherits the capability without any
 * block-specific frontend code.
 */

/** Config key carrying the remembered-decision record. Mirrors the backend. */
export const INTERACTIVE_MEMORY_KEY = "interactive_memory";

export interface InteractiveMemoryRecord {
  /** When true, the engine replays {@link decision} if {@link signature} still matches. */
  enabled: boolean;
  /** The user's verbatim ``interactive_response`` (block-agnostic). */
  decision?: Record<string, unknown> | null;
  /** The input fingerprint captured when the decision was saved. */
  signature?: Record<string, string[]> | null;
}

/**
 * Read the memory record from a node config.
 *
 * #2412: the record lives at ``config.params.interactive_memory``. A legacy
 * record at the config top level is used only when ``params`` has none, so a
 * params record (including a disabled or cleared one) always wins. Mirrors the
 * backend ``load_interactive_memory``. Writers go through ``mergeNodeConfig``,
 * which stores the record under ``params`` and drops the top-level copy.
 */
export function readInteractiveMemory(
  config: Record<string, unknown> | undefined | null,
): InteractiveMemoryRecord | null {
  if (!config) return null;
  const params = config.params as Record<string, unknown> | undefined;
  const nested = params && typeof params === "object" ? params[INTERACTIVE_MEMORY_KEY] : undefined;
  const raw = nested ?? config[INTERACTIVE_MEMORY_KEY];
  return raw && typeof raw === "object" ? (raw as InteractiveMemoryRecord) : null;
}

/**
 * #2412: true when an interactive prompt's block id is not a node of the canvas
 * it would be remembered on. A block inside an expanded subworkflow runs
 * flattened as ``<subworkflowNodeId>__<innerId>``, so the parent canvas has no
 * such node and memory cannot be stored for it.
 */
export function isPromptOutsideCanvas(
  blockId: string,
  nodes: ReadonlyArray<{ id: string }>,
): boolean {
  return !nodes.some((node) => node.id === blockId);
}

/** One-line explanation shown where "remember" is unavailable (#2412). */
export const SUBWORKFLOW_MEMORY_UNSUPPORTED =
  "Remembering a choice isn't available for blocks inside a subworkflow. The dialog opens on every run.";

/** True when a block schema describes an interactive block (ADR-051). */
export function isInteractiveBlock(executionMode: string | null | undefined): boolean {
  return executionMode === "interactive";
}
