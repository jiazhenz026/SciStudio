/**
 * Type definitions for ADR-039 §3.5a conflict-marker decorations.
 *
 * Extracted from `ConflictMarkerDecoration.ts` (#1422) to keep each
 * produced module ≤ 500 LOC. No runtime code — only `interface`
 * declarations — so this module is dependency-free.
 */

/**
 * A single parsed conflict region. Lines are 1-based (Monaco
 * convention). Whole-file character offsets are NOT included; the
 * decoration provider derives them from Monaco's `model.getLineContent`.
 */
export interface ConflictRegion {
  /** 1-based: the line containing `<<<<<<<`. */
  startLine: number;
  /**
   * 1-based: in default 2-way style this is the `=======` line; in
   * diff3 style this is the `|||||||` line.
   */
  currentEndLine: number;
  /**
   * Diff3 only: the `=======` line. `null` for default 2-way style.
   */
  baseEndLine: number | null;
  /** 1-based: the `>>>>>>>` line. */
  incomingEndLine: number;
  /** Branch label after `<<<<<<<`, or "current" if absent. */
  currentLabel: string;
  /** Branch label after `>>>>>>>`, or "incoming" if absent. */
  incomingLabel: string;
}

/** Actions a user can invoke on a conflict region. */
export interface ConflictAction {
  type: "accept_current" | "accept_incoming" | "accept_both" | "manual_edit";
}
