/**
 * ADR-039 §3.5 — GitDiffModal (SKELETON).
 *
 * Purpose
 * -------
 * Modal viewer for a unified diff returned by `GET /api/git/diff`. Renders
 * via `react-diff-viewer-continued` (already in the SciEasy dep tree —
 * D39-2.3b will add the import; the package is bundle-safe and tree-shakes
 * to ~30 KB). ADR §3.5 line 219.
 *
 * Props
 * -----
 *   open:        boolean
 *   onClose:     () => void
 *   from:        string           — commit SHA, "HEAD", or branch name
 *   to?:         string           — defaults to "WORKING" (working tree)
 *   file?:       string           — restrict diff to a single file
 *   title?:      string           — override default title
 *
 * State (component-local)
 * -----------------------
 *   loading:     boolean
 *   diffText:    string | null
 *   error:       string | null
 *
 * Fetch flow
 * ----------
 *   useEffect on `open && from`:
 *     setLoading(true);
 *     api.gitDiff({from, to, file}).then(({diff}) => setDiffText(diff)).
 *       catch(err => setError(err.message)).finally(() => setLoading(false))
 *
 * Layout markup
 * -------------
 *   <Dialog open=...>
 *     <DialogContent data-testid="git-diff-modal" className="max-w-5xl">
 *       <DialogTitle>{title ?? `Diff ${from}…${to}`}</DialogTitle>
 *       {loading ? <Spinner data-testid="git-diff-loading"/> :
 *        error ? <div role="alert" data-testid="git-diff-error">{error}</div> :
 *        diffText === "" ?
 *          <div data-testid="git-diff-empty">No differences.</div> :
 *          <ReactDiffViewer
 *            data-testid="git-diff-viewer"
 *            // The library accepts unified-diff via splitText prop or
 *            // explicit oldValue/newValue. D39-2.3b parses the unified
 *            // diff (or uses the library's `compareMethod="diffWords"`
 *            // directly with parsed hunks). Implementation choice
 *            // documented in the test.
 *          />
 *       }
 *       <DialogFooter>
 *         <Button data-testid="git-diff-close" onClick={onClose}>Close</Button>
 *       </DialogFooter>
 *     </DialogContent>
 *   </Dialog>
 *
 * Copy strings
 * ------------
 *   - Title fallback:    "Diff {from} → {to}"
 *   - Empty:             "No differences."
 *   - Loading:           "Loading diff…"
 *   - Close button:      "Close"
 *
 * Keyboard shortcuts
 * ------------------
 *   - Esc → onClose()
 *
 * Accessibility
 * -------------
 *   - Dialog uses Radix's labelledby plumbing.
 *   - Error region role="alert".
 *
 * Edge cases
 * ----------
 *   - from === undefined or null: render error "No commit selected."
 *   - Backend 404 (unknown SHA): error region surfaces the server detail.
 *   - Large diffs (> 200 KB text): D39-2.3b should still render but may
 *     warn at the top: "Large diff — rendering may be slow."
 *     (Threshold tunable; out of scope for skeleton.)
 *
 * Tests (see vitest):
 *   - fetches /api/git/diff on open
 *   - renders loading state initially
 *   - renders error state on API failure
 *   - renders "No differences." when diff response is empty
 */
import type { JSX } from "react";

export interface GitDiffModalProps {
  open: boolean;
  onClose: () => void;
  from: string;
  to?: string;
  file?: string;
  title?: string;
}

export function GitDiffModal(_props: GitDiffModalProps): JSX.Element {
  // TODO: D39-2.3b — implement markup + fetch flow + react-diff-viewer-continued
  // integration. Add the npm dependency in package.json as part of the
  // impl PR (skeleton avoids touching package.json).
  throw new Error("TODO: D39-2.3b — implement GitDiffModal body");
}
