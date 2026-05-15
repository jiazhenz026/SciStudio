/**
 * ADR-039 §3.5 — CommitDialog (SKELETON).
 *
 * Purpose
 * -------
 * Modal that the user opens via the toolbar "Commit" button (or the
 * Ctrl+K, C chord shortcut). It shows a multi-line message editor
 * pre-filled with a template that includes the list of modified files
 * (from `GET /api/git/status`), then POSTs to `/api/git/commit` and
 * closes on success. ADR §3.5 lines 217-244.
 *
 * Props
 * -----
 *   open:                  boolean          — controls modal visibility.
 *   onClose:               () => void       — called on Cancel / Esc / success.
 *   initialFiles?:         string[]         — if caller wants to scope this
 *                                              commit to specific files only.
 *                                              When omitted, the dialog
 *                                              commits all tracked changes.
 *   defaultAuthor?:        string           — pre-fills the (optional) author
 *                                              line; usually `null` for v1.
 *   onCommitSuccess?:      (sha: string) => void — fired after the slice
 *                                              `commit(...)` returns; gives
 *                                              callers a hook to toast or
 *                                              trigger a focus jump to history.
 *
 * State shape (component-local)
 * ----------------------------
 *   message:        string   — bound to the textarea.
 *   submitting:     boolean  — disables Commit button + spinner.
 *   localError:     string|null — shown inline below the textarea.
 *
 * Slice state read (`useAppStore`)
 * --------------------------------
 *   status:         GitStatus | null — to render the auto-detected file list.
 *   lastError:      string | null   — slice-level error (e.g. "nothing to commit").
 *
 * Layout markup (data-testid attrs are the test contract — DO NOT rename
 * without updating the vitest tests in CommitDialog.test.tsx)
 * ---------------------------------------------------------
 *   <Dialog open=...>
 *     <DialogContent data-testid="commit-dialog">
 *       <DialogTitle>Commit changes</DialogTitle>
 *       <textarea
 *         data-testid="commit-dialog-message"
 *         className="font-mono"
 *         placeholder={DEFAULT_TEMPLATE}
 *         value={message}
 *         onChange={...}
 *         rows={12}
 *       />
 *       <ul data-testid="commit-dialog-files">
 *         {status?.modified.map(...)}
 *         {status?.staged.map(...)}
 *         {status?.untracked.map(...)}
 *       </ul>
 *       <div role="alert" data-testid="commit-dialog-error">{localError}</div>
 *       <DialogFooter>
 *         <Button data-testid="commit-dialog-cancel" onClick={onClose}>Cancel</Button>
 *         <Button data-testid="commit-dialog-submit" onClick={onSubmit}>Commit</Button>
 *       </DialogFooter>
 *     </DialogContent>
 *   </Dialog>
 *
 * Pre-filled template (passed as textarea placeholder; user can edit freely):
 * --------------------------------------------------------------------------
 *   <one-line subject>
 *
 *   # What changed:
 *   # - workflows/<id>.yaml: …
 *   # - blocks/<file>.py:    …
 *
 *   # Auto-detected modified files:
 *   #   M  workflows/image_pipeline.yaml
 *   #   M  blocks/cellpose_wrap.py
 *   #   A  notes/2026-05-15-thoughts.md
 *
 * On submit:
 *   1. Strip lines starting with "#" (comments) — git plumbing accepts the
 *      raw string, but we mimic git's user-facing strip-comments behaviour
 *      so commits look like ordinary git commits.
 *   2. If after stripping the message is empty → set localError = "Commit
 *      message cannot be empty." and abort.
 *   3. Call gitSlice.commit(stripped, initialFiles).
 *   4. On success: onCommitSuccess?.(sha); onClose().
 *   5. On error: localError = err.message; keep dialog open so user can
 *      edit and retry.
 *
 * Copy strings (English, v1):
 *   - Title:             "Commit changes"
 *   - Submit button:     "Commit"
 *   - Cancel button:     "Cancel"
 *   - Empty validation:  "Commit message cannot be empty."
 *   - Submitting label:  "Committing…"
 *   - No changes hint:   "No changes to commit." (shown when status is clean;
 *                        disables submit button)
 *
 * Keyboard shortcuts
 * ------------------
 *   - Esc                 → onClose()
 *   - Ctrl+Enter          → submit (matches the toolbar Run shortcut style)
 *   - Tab / Shift+Tab     → navigate between textarea ↔ buttons normally
 *
 * Accessibility
 * -------------
 *   - <Dialog> has aria-labelledby set to the DialogTitle id (Radix gives
 *     us this for free).
 *   - localError region MUST be role="alert" aria-live="assertive" so
 *     screen readers announce validation failures.
 *   - Textarea has aria-describedby pointing at a hidden helper text
 *     explaining the commit-message convention.
 *
 * Edge cases
 * ----------
 *   - status === null (not yet loaded): show "Loading file list…" placeholder
 *     in the file list UL; submit button disabled until status loaded.
 *   - status.dirty === false: render "No changes to commit." inline; submit
 *     button disabled.
 *   - 409 from backend (nothing to commit / stale): keep dialog open, show
 *     server error in localError.
 *   - 503 from backend (BundledGitMissing): localError = "Git binary not
 *     available. Reinitialize from Settings → Git."
 *
 * Tests (see CommitDialog.test.tsx)
 * ---------------------------------
 *   - it renders with default template in textarea placeholder
 *   - it shows the modified-file list from gitSlice.status
 *   - it disables Submit when message empty after stripping comments
 *   - it calls gitSlice.commit with stripped message and initialFiles
 *   - it surfaces server errors inline without closing the dialog
 */
import type { JSX } from "react";

import type { GitStatus } from "../../types/api";

export interface CommitDialogProps {
  open: boolean;
  onClose: () => void;
  initialFiles?: string[];
  defaultAuthor?: string;
  onCommitSuccess?: (sha: string) => void;
}

/**
 * Default commit-message template per ADR §3.5 line 230. Exported so the
 * implementation phase and the tests can reference one source of truth
 * (the test asserts the placeholder begins with this string).
 */
export const COMMIT_TEMPLATE = `<one-line subject>

# What changed:
# - workflows/<id>.yaml: …
# - blocks/<file>.py:    …
`;

/**
 * Strip git-style comment lines (those starting with "#"). Returns the
 * stripped message with surrounding whitespace trimmed.
 * Implementation: pure helper, safe to keep in skeleton.
 */
export function stripCommentLines(message: string): string {
  return message
    .split("\n")
    .filter((line) => !line.startsWith("#"))
    .join("\n")
    .trim();
}

/**
 * Render an auto-detected files block (read-only, prepended into the
 * placeholder). Pure helper, safe to keep in skeleton.
 *
 * Example output:
 *   # Auto-detected modified files:
 *   #   M  workflows/image_pipeline.yaml
 *   #   A  notes/2026-05-15-thoughts.md
 */
export function formatAutoDetectedFiles(status: GitStatus | null): string {
  if (!status) return "";
  const lines: string[] = ["# Auto-detected modified files:"];
  for (const f of status.modified) lines.push(`#   M  ${f}`);
  for (const f of status.staged) lines.push(`#   S  ${f}`);
  for (const f of status.untracked) lines.push(`#   A  ${f}`);
  return lines.join("\n");
}

export function CommitDialog(_props: CommitDialogProps): JSX.Element {
  // TODO: D39-2.3b — wire to gitSlice.commit + render the dialog markup
  // described above (Dialog from shadcn, textarea, file list, error
  // region, Cancel + Commit buttons).
  throw new Error("TODO: D39-2.3b — implement CommitDialog body");
}
