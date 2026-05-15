/**
 * ADR-039 §3.5 + §3.7 — StashListPanel (SKELETON).
 *
 * Purpose
 * -------
 * Side drawer surfacing the full stash list (`GET /api/git/stash`). Lets
 * the user inspect, apply (without dropping), or drop any stash entry,
 * plus create a new stash from the current working tree. Reached via a
 * toolbar overflow menu item (D39-2.3b decides exact entry point — likely
 * the same overflow menu as "Cherry-pick…").
 *
 * Props
 * -----
 *   open:        boolean
 *   onClose:     () => void
 *
 * Slice state read
 * ----------------
 *   stashes:       GitStashEntry[] | null
 *   loadStashes:   () => Promise<void>
 *
 * Event flow
 * ----------
 *   - mount / open=true → loadStashes()
 *   - "New stash" button → opens a small inline prompt for an optional
 *     message → POST /api/git/stash/save.
 *   - per-row "Apply" → POST /api/git/stash/apply (handles conflict
 *     response by handing off to MergeFlow — D39-2.4a).
 *   - per-row "Drop" → DELETE /api/git/stash/{stash_id} with a confirm.
 *
 * Layout markup
 * -------------
 *   <Sheet open=... onOpenChange=...>
 *     <SheetContent data-testid="stash-list-panel" side="right">
 *       <SheetHeader>
 *         <SheetTitle>Stashes</SheetTitle>
 *         <Button data-testid="stash-list-new" onClick={onNewStash}>
 *           New stash…
 *         </Button>
 *       </SheetHeader>
 *       {stashes === null ? <Spinner data-testid="stash-list-loading"/> :
 *        stashes.length === 0 ?
 *          <div data-testid="stash-list-empty">No stashes yet.</div> :
 *          <ul data-testid="stash-list-rows" role="list">
 *            {stashes.map(s => (
 *              <li
 *                key={s.stash_id}
 *                data-testid={`stash-row-${s.index}`}
 *              >
 *                <div>
 *                  <span data-testid="stash-row-id">{s.stash_id}</span>
 *                  <span data-testid="stash-row-msg">{s.message}</span>
 *                  <time data-testid="stash-row-date">{s.created_at}</time>
 *                </div>
 *                <Button data-testid={`stash-row-apply-${s.index}`}
 *                        onClick={() => onApply(s.stash_id)}>
 *                  Apply
 *                </Button>
 *                <Button data-testid={`stash-row-drop-${s.index}`}
 *                        variant="destructive"
 *                        onClick={() => onDrop(s.stash_id)}>
 *                  Drop
 *                </Button>
 *              </li>
 *            ))}
 *          </ul>
 *       }
 *     </SheetContent>
 *   </Sheet>
 *
 * Copy strings
 * ------------
 *   Title:        "Stashes"
 *   Empty state:  "No stashes yet."
 *   Loading:      "Loading stashes…"
 *   New button:   "New stash…"
 *   Apply button: "Apply"
 *   Drop button:  "Drop"
 *   Drop confirm: "Drop stash '{stashId}'? This cannot be undone."
 *   New prompt:   "Stash message (optional):"
 *
 * Keyboard shortcuts
 * ------------------
 *   - Esc closes the sheet
 *   - Up/Down moves focus through rows
 *   - A on focused row → Apply (no confirm)
 *   - D on focused row → Drop (with confirm)
 *
 * Accessibility
 * -------------
 *   - role="list" + role="listitem" on rows
 *   - Drop buttons have aria-describedby pointing at hidden helper
 *     text: "Drop permanently deletes this stash."
 *   - Sheet title is the <SheetTitle> Radix gives us aria-labelledby for
 *     free.
 *
 * Edge cases
 * ----------
 *   - Apply returns a conflict (status === "conflict"):
 *       1. Stash is NOT dropped (matches `git stash apply` semantics).
 *       2. Hand the conflicted_files off to MergeFlow (D39-2.4a) — the
 *          conflict resolution UI is shared.
 *   - "Apply and drop" affordance: NOT in v1 scope (per ADR §3.5 — the
 *     v1 surface is list/save/apply/drop, not pop). Out of scope here.
 *
 * Tests
 * -----
 *   - renders empty state when stashes === []
 *   - renders one row per stash entry
 *   - clicking Apply dispatches gitStashApply
 *   - clicking Drop dispatches gitStashDrop after confirm
 *   - New stash button opens prompt and dispatches gitStashSave
 */
import type { JSX } from "react";

export interface StashListPanelProps {
  open: boolean;
  onClose: () => void;
}

export function StashListPanel(_props: StashListPanelProps): JSX.Element {
  // TODO: D39-2.3b — implement Sheet body, wire loadStashes on open,
  // render rows + Apply / Drop handlers.
  throw new Error("TODO: D39-2.3b — implement StashListPanel body");
}
