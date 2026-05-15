/**
 * ADR-039 §3.5 + §3.7 — BranchPicker (SKELETON).
 *
 * Purpose
 * -------
 * Toolbar dropdown that:
 *   1. Shows the current branch name as the trigger label.
 *   2. Lists all local branches with a checkmark next to the current one.
 *   3. Click on a non-current branch → switch (dirty-tree → stash dialog).
 *   4. "Create branch…" menu item → modal asking name + base.
 *   5. "Delete branch…" menu item → confirmation dialog.
 *   6. "Merge into current →" submenu listing other branches (D39-2.4a
 *      installs the MergeFlow modal; skeleton just dispatches an event).
 *   7. "Cherry-pick…" item (D39-2.4a installs the cherry-pick flow).
 *
 * Props
 * -----
 *   onMergeRequested?:        (sourceBranch: string) => void
 *   onCherryPickRequested?:   () => void
 *   onCreateBranchRequested?: () => void   — opens the create-branch modal
 *
 * Slice state read
 * ----------------
 *   branches:        GitBranch[] | null
 *   currentBranch:   string | null
 *   loadBranches:    () => Promise<void>
 *   switchBranch:    (name) => Promise<void>
 *   deleteBranch:    (name, force?) => Promise<void>
 *
 * Event flow
 * ----------
 *   - mount → loadBranches()
 *   - click non-current branch → switchBranch(name)
 *     If dirty: backend auto-stashes; UI shows toast or StashApplyDialog.
 *   - click "Create branch…" → onCreateBranchRequested?.() OR open a local
 *     modal (impl phase decides).
 *   - click "Delete X" → confirm → deleteBranch(name)
 *   - click "Merge X into current" → onMergeRequested?.(name)
 *
 * Layout markup
 * -------------
 *   <DropdownMenu>
 *     <DropdownMenuTrigger asChild>
 *       <Button
 *         variant="toolbar" size="toolbar"
 *         data-testid="branch-picker-trigger"
 *       >
 *         <GitBranchIcon className="size-3.5"/>
 *         {currentBranch ?? "no branch"}
 *         <ChevronDown className="size-3"/>
 *       </Button>
 *     </DropdownMenuTrigger>
 *     <DropdownMenuContent data-testid="branch-picker-menu" align="start">
 *       <DropdownMenuLabel>Switch to branch</DropdownMenuLabel>
 *       {branches?.map((b) => (
 *         <DropdownMenuItem
 *           key={b.name}
 *           data-testid={`branch-picker-item-${b.name}`}
 *           onClick={() => onSwitch(b.name)}
 *           disabled={b.is_current}
 *         >
 *           <span data-testid="branch-picker-item-check">{b.is_current ? "✓" : " "}</span>
 *           {b.name}
 *         </DropdownMenuItem>
 *       ))}
 *       <DropdownMenuSeparator />
 *       <DropdownMenuItem
 *         data-testid="branch-picker-create"
 *         onClick={onCreateBranchRequested}
 *       >
 *         + Create branch…
 *       </DropdownMenuItem>
 *       <DropdownMenuSub>
 *         <DropdownMenuSubTrigger data-testid="branch-picker-merge-sub">
 *           Merge into current
 *         </DropdownMenuSubTrigger>
 *         <DropdownMenuSubContent>
 *           {branches?.filter((b) => !b.is_current).map((b) => (
 *             <DropdownMenuItem
 *               key={b.name}
 *               data-testid={`branch-picker-merge-${b.name}`}
 *               onClick={() => onMergeRequested?.(b.name)}
 *             >
 *               {b.name}
 *             </DropdownMenuItem>
 *           ))}
 *         </DropdownMenuSubContent>
 *       </DropdownMenuSub>
 *       <DropdownMenuItem
 *         data-testid="branch-picker-cherry-pick"
 *         onClick={onCherryPickRequested}
 *       >
 *         Cherry-pick…
 *       </DropdownMenuItem>
 *     </DropdownMenuContent>
 *   </DropdownMenu>
 *
 * Copy strings
 * ------------
 *   Trigger fallback:  "no branch" (when currentBranch is null)
 *   Section header:    "Switch to branch"
 *   Create label:      "+ Create branch…"
 *   Merge sub-label:   "Merge into current"
 *   Cherry-pick label: "Cherry-pick…"
 *   Delete confirm:    "Delete branch '{name}'? This cannot be undone."
 *
 * Keyboard shortcuts (within dropdown — Radix gives most for free)
 * ----------------------------------------------------------------
 *   - Up/Down navigate items
 *   - Enter activates focused item
 *   - Esc closes
 *   - Tab moves focus out
 *
 * Accessibility
 * -------------
 *   - Trigger button uses aria-label="Current branch: {currentBranch}"
 *     so screen readers don't read the icon as "git-branch-icon".
 *   - Each menu item with the check mark uses aria-current="true"
 *     when is_current.
 *
 * Edge cases
 * ----------
 *   - branches === null (not yet loaded): trigger shows "loading…" label,
 *     menu shows a single disabled "Loading branches…" item.
 *   - branches === []: impossible on a real repo (initial commit creates
 *     `main`), but defensively render "No local branches" disabled item.
 *   - Switch while dirty: switchBranch() resolves with the auto-stashed
 *     state from the backend; D39-2.3b opens StashApplyDialog.
 *   - Delete the current branch: backend returns 409; surface as
 *     gitSlice.lastError, BranchPicker shows toast.
 *
 * Tests (see BranchPicker.test.tsx)
 * ---------------------------------
 *   - shows current branch name in trigger
 *   - renders one DropdownMenuItem per branch with checkmark on current
 *   - clicking a non-current branch calls gitSlice.switchBranch
 *   - "Create branch…" menu item calls onCreateBranchRequested
 *   - merge submenu shows only non-current branches
 *   - clicking a merge submenu item calls onMergeRequested
 */
import type { JSX } from "react";

export interface BranchPickerProps {
  onMergeRequested?: (sourceBranch: string) => void;
  onCherryPickRequested?: () => void;
  onCreateBranchRequested?: () => void;
}

export function BranchPicker(_props: BranchPickerProps): JSX.Element {
  // TODO: D39-2.3b — implement using shadcn DropdownMenu + Radix submenu;
  // dispatch loadBranches() on mount.
  throw new Error("TODO: D39-2.3b — implement BranchPicker body");
}
