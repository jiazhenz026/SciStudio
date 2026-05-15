/**
 * ADR-039 §3.6 — StashApplyDialog (SKELETON).
 *
 * Purpose
 * -------
 * When the user restores a prior version while the working tree is dirty,
 * the backend auto-stashes the working changes (`git stash push -m
 * "auto-stash before restore"`) and returns the new `stash_id`. This
 * dialog then prompts:
 *
 *     "Your unsaved changes are stashed. Apply them?
 *      [Apply now] [Keep stashed] [Discard]"
 *
 * Per ADR §3.6 — the wording is part of the contract.
 *
 * Props
 * -----
 *   open:           boolean
 *   stashId:        string                 — passed from gitSlice.restore result
 *   onClose:        () => void
 *   onApplyNow:     (stashId) => Promise<void>  — defaults to gitSlice.stashApply
 *   onKeepStashed:  () => void              — defaults to onClose
 *   onDiscard:      (stashId) => Promise<void> — defaults to gitSlice.stashDrop
 *
 * Layout markup
 * -------------
 *   <Dialog open=...>
 *     <DialogContent data-testid="stash-apply-dialog">
 *       <DialogTitle>Your unsaved changes are stashed.</DialogTitle>
 *       <p data-testid="stash-apply-dialog-body">
 *         The restore put your previous edits into stash {stashId}.
 *         Apply them on top of the restored version?
 *       </p>
 *       <DialogFooter>
 *         <Button data-testid="stash-apply-discard" variant="destructive"
 *                 onClick={() => onDiscard(stashId).then(onClose)}>
 *           Discard
 *         </Button>
 *         <Button data-testid="stash-apply-keep"
 *                 variant="ghost"
 *                 onClick={onKeepStashed}>
 *           Keep stashed
 *         </Button>
 *         <Button data-testid="stash-apply-now"
 *                 variant="default"
 *                 onClick={() => onApplyNow(stashId).then(onClose)}>
 *           Apply now
 *         </Button>
 *       </DialogFooter>
 *     </DialogContent>
 *   </Dialog>
 *
 * Copy strings (LITERAL — matches ADR §3.6)
 * -----------------------------------------
 *   Title:           "Your unsaved changes are stashed."
 *   Body:            "The restore put your previous edits into stash
 *                     {stashId}. Apply them on top of the restored version?"
 *   Apply button:    "Apply now"
 *   Keep button:     "Keep stashed"
 *   Discard button:  "Discard"
 *   Discard confirm: "This permanently drops the stash. Continue?"
 *
 * Keyboard shortcuts
 * ------------------
 *   - Enter         → Apply now (default action)
 *   - Esc           → Keep stashed
 *   - Backspace+Del → no-op (don't make Discard the default destructive)
 *
 * Accessibility
 * -------------
 *   - Default-focused button on open: "Apply now" (matches Enter binding).
 *   - Destructive Discard button has aria-describedby pointing at a
 *     hidden helper region: "This permanently deletes the stash."
 *
 * Edge cases
 * ----------
 *   - stashApply returns {status: "conflict", conflicted_files}: dialog
 *     should NOT auto-close; it should hand off to MergeFlow (D39-2.4a).
 *     Skeleton documents this; impl phase wires the handoff.
 *   - User clicks Apply now while another stashApply is in flight:
 *     submitting flag disables all buttons; impl phase responsibility.
 *
 * Tests
 * -----
 *   - renders title + body with the stash id substituted
 *   - Apply now button calls onApplyNow with stashId
 *   - Discard button calls onDiscard with stashId after user confirm
 *   - Keep stashed button just closes the dialog
 */
import type { JSX } from "react";

export interface StashApplyDialogProps {
  open: boolean;
  stashId: string;
  onClose: () => void;
  onApplyNow?: (stashId: string) => Promise<void>;
  onKeepStashed?: () => void;
  onDiscard?: (stashId: string) => Promise<void>;
}

export function StashApplyDialog(_props: StashApplyDialogProps): JSX.Element {
  // TODO: D39-2.3b — implement Dialog body + the three action handlers
  // with their default gitSlice fallbacks.
  throw new Error("TODO: D39-2.3b — implement StashApplyDialog body");
}
