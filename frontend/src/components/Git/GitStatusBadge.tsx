/**
 * ADR-039 §3.5 — GitStatusBadge (SKELETON).
 *
 * Purpose
 * -------
 * Compact toolbar pill showing the working-tree state at a glance:
 *   - Clean (green dot)            — status.dirty === false
 *   - Dirty (amber dot + N files)  — status.dirty === true
 *   - Conflicted (red dot)         — status.conflicted.length > 0
 *   - Loading / unknown (grey dot) — status === null
 *
 * Clicking the badge opens the CommitDialog (or focuses it if it's
 * already open). On hover, a tooltip shows the file lists.
 *
 * Props
 * -----
 *   onClick?:   () => void   — defaults to opening CommitDialog via
 *                              a slice-level open flag (introduced by
 *                              D39-2.3b). The skeleton just calls
 *                              the prop if provided.
 *
 * Slice state read
 * ----------------
 *   status:      GitStatus | null
 *   loadStatus:  () => Promise<void>
 *
 * Event flow
 * ----------
 *   - mount → loadStatus()
 *   - WS `git.head_changed` → invalidateHistory clears status → re-fetch
 *     happens lazily next render. (D39-2.3b: add an explicit re-fetch on
 *     status === null to avoid stale-blank-pill state.)
 *
 * Layout markup
 * -------------
 *   <Tooltip>
 *     <TooltipTrigger asChild>
 *       <button
 *         data-testid="git-status-badge"
 *         data-status={statusKey}  // "clean" | "dirty" | "conflict" | "unknown"
 *         onClick={onClick}
 *         className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs"
 *       >
 *         <span data-testid="git-status-badge-dot" className={dotClassFor(statusKey)} />
 *         {label}
 *       </button>
 *     </TooltipTrigger>
 *     <TooltipContent data-testid="git-status-badge-tooltip">
 *       <ul>
 *         {status.modified.map(f => <li>M  {f}</li>)}
 *         {status.staged.map(f => <li>S  {f}</li>)}
 *         {status.untracked.map(f => <li>?  {f}</li>)}
 *         {status.conflicted.map(f => <li>U  {f}</li>)}
 *       </ul>
 *     </TooltipContent>
 *   </Tooltip>
 *
 * Copy strings
 * ------------
 *   Clean label:        "clean"
 *   Dirty label:        "{n} change{n>1?"s":""}"   e.g. "3 changes"
 *   Conflict label:     "{n} conflict{n>1?"s":""}"
 *   Unknown label:      "git: loading…"
 *   Tooltip header:     "Working tree:"
 *   Tooltip clean text: "No uncommitted changes."
 *
 * Dot color mapping
 * -----------------
 *   clean      → bg-pine (green; matches WS connected pill)
 *   dirty      → bg-amber-500
 *   conflict   → bg-red-500
 *   unknown    → bg-stone-400
 *
 * Keyboard shortcuts
 * ------------------
 *   - Enter on focused badge → onClick()
 *
 * Accessibility
 * -------------
 *   - aria-label uses the statusKey + the file count so screen readers
 *     announce "git: 3 changes, 0 conflicts" rather than "button, clean".
 *   - Tooltip uses Radix's aria-describedby pattern.
 *
 * Edge cases
 * ----------
 *   - status === null and no project: render hidden (don't show
 *     "loading…" forever when there's nothing to load).
 *   - conflicted.length > 0 takes precedence over dirty (a conflicted tree
 *     is also dirty, but the user needs to be alerted to conflicts first).
 *
 * Tests
 * -----
 *   - renders "clean" when status.dirty === false
 *   - renders dirty file count when status.modified.length > 0
 *   - renders conflict count when status.conflicted.length > 0
 *   - clicking dispatches onClick prop
 */
import type { JSX } from "react";

export interface GitStatusBadgeProps {
  onClick?: () => void;
}

export function GitStatusBadge(_props: GitStatusBadgeProps): JSX.Element {
  // TODO: D39-2.3b — implement badge markup, dispatch loadStatus on mount,
  // compute statusKey from gitSlice.status, render dot + label + tooltip.
  throw new Error("TODO: D39-2.3b — implement GitStatusBadge body");
}
