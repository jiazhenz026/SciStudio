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

/** Read the memory record from a node config (checks top level and ``params``). */
export function readInteractiveMemory(
  config: Record<string, unknown> | undefined | null,
): InteractiveMemoryRecord | null {
  if (!config) return null;
  const params = config.params as Record<string, unknown> | undefined;
  const raw = config[INTERACTIVE_MEMORY_KEY] ?? params?.[INTERACTIVE_MEMORY_KEY];
  return raw && typeof raw === "object" ? (raw as InteractiveMemoryRecord) : null;
}

/** True when a block schema describes an interactive block (ADR-051). */
export function isInteractiveBlock(executionMode: string | null | undefined): boolean {
  return executionMode === "interactive";
}
