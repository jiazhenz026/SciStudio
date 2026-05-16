/**
 * ADR-039 §3.5 + §3.7 — BranchPicker.
 *
 * Toolbar dropdown:
 *   1. Trigger label = currentBranch.
 *   2. Lists local branches with checkmark on current.
 *   3. Click non-current → gitSlice.switchBranch.
 *   4. "Create branch…" item → opens an inline prompt for name + (optional)
 *      base SHA, then dispatches gitSlice.createBranch.
 *   5. "Merge X into current" item per non-current branch → dispatches
 *      onMergeRequested (handled by MergeFlow in D39-2.4a).
 *   6. "Cherry-pick…" item → dispatches onCherryPickRequested.
 *
 * The shadcn DropdownMenu primitive does not yet wrap Radix's Sub menu, so
 * the merge "submenu" is rendered as a separator block of items inside
 * the main menu. The visual hierarchy is preserved via a label header.
 */
import { GitBranch as GitBranchIcon, ChevronDown, Plus, Check, GitMerge, Trash2, CornerUpRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { useAppStore } from "../../store";

export interface BranchPickerProps {
  onMergeRequested?: (sourceBranch: string) => void;
  onCherryPickRequested?: () => void;
  onCreateBranchRequested?: () => void;
}

export function BranchPicker(props: BranchPickerProps): JSX.Element {
  const branches = useAppStore((s) => s.branches);
  const currentBranch = useAppStore((s) => s.currentBranch);
  const loadBranches = useAppStore((s) => s.loadBranches);
  const switchBranch = useAppStore((s) => s.switchBranch);
  const createBranch = useAppStore((s) => s.createBranch);
  const deleteBranch = useAppStore((s) => s.deleteBranch);
  const currentProject = useAppStore((s) => s.currentProject);

  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");

  // Reload branches whenever the active project changes (Codex P1-A on PR #940):
  // the `branches` cache lives in a global slice and is not cleared by
  // `setCurrentProject`, so a stale branch list would survive a project
  // switch and let the picker dispatch actions against the previous repo.
  // Keying on the project id guarantees a fresh fetch per project.
  const currentProjectId = currentProject?.id ?? null;
  useEffect(() => {
    if (!currentProjectId) return;
    void loadBranches();
  }, [currentProjectId, loadBranches]);

  const handleSwitch = useCallback(
    (name: string) => {
      void switchBranch(name).catch((err) => {
        // Error is already surfaced via gitSlice.lastError; log for diagnosis.
        // eslint-disable-next-line no-console
        console.warn("[BranchPicker] switchBranch failed:", err);
      });
    },
    [switchBranch],
  );

  const handleCreate = useCallback(() => {
    if (props.onCreateBranchRequested) {
      props.onCreateBranchRequested();
      return;
    }
    setNewName("");
    setCreateOpen(true);
  }, [props]);

  const submitCreate = useCallback(() => {
    const name = newName.trim();
    if (!name) {
      setCreateOpen(false);
      return;
    }
    void createBranch(name)
      .then(() => switchBranch(name))
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[BranchPicker] createBranch failed:", err);
      })
      .finally(() => {
        setCreateOpen(false);
        setNewName("");
      });
  }, [createBranch, newName, switchBranch]);

  const handleDelete = useCallback(
    (name: string) => {
      const confirmed = window.confirm(
        `Delete branch '${name}'? This cannot be undone.`,
      );
      if (!confirmed) return;
      void deleteBranch(name).catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[BranchPicker] deleteBranch failed:", err);
      });
    },
    [deleteBranch],
  );

  const triggerLabel = currentBranch ?? (branches === null ? "loading…" : "no branch");

  const nonCurrent = (branches ?? []).filter((b) => !b.is_current);

  // #984 Option A fix: re-fetch on dropdown open when the cache is null.
  // The mount-time useEffect only fires on `currentProjectId` change, so any
  // mid-session invalidation that doesn't go through `invalidateHistory`
  // (which now refetches as of the sibling fix) plus the small window where
  // a stale render shows branches=null between createBranch's reset and the
  // awaited loadBranches resolving — both leave the dropdown stuck on
  // "Loading branches…". Triggering loadBranches on every open-when-null is
  // cheap (1 GET, ~200ms) and guarantees the dropdown is always live.
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open && branches === null && currentProjectId) {
        void loadBranches();
      }
    },
    [branches, currentProjectId, loadBranches],
  );

  return (
    <>
      <DropdownMenu onOpenChange={handleOpenChange}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="toolbar"
            size="toolbar"
            type="button"
            data-testid="branch-picker-trigger"
            aria-label={`Current branch: ${currentBranch ?? "none"}`}
          >
            <GitBranchIcon className="size-3.5" />
            {triggerLabel}
            <ChevronDown className="size-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          data-testid="branch-picker-menu"
          align="start"
          className="min-w-[14rem]"
        >
          <DropdownMenuLabel>Switch to branch</DropdownMenuLabel>
          {branches === null ? (
            <DropdownMenuItem disabled>
              <span className="text-stone-400">Loading branches…</span>
            </DropdownMenuItem>
          ) : branches.length === 0 ? (
            <DropdownMenuItem disabled>
              <span className="text-stone-400">No local branches</span>
            </DropdownMenuItem>
          ) : (
            branches.map((b) => (
              <DropdownMenuItem
                key={b.name}
                data-testid={`branch-picker-item-${b.name}`}
                disabled={b.is_current}
                aria-current={b.is_current ? "true" : undefined}
                onSelect={(e) => {
                  if (b.is_current) {
                    e.preventDefault();
                    return;
                  }
                  handleSwitch(b.name);
                }}
              >
                <span
                  data-testid="branch-picker-item-check"
                  className="inline-block w-4"
                >
                  {b.is_current ? <Check className="size-3.5 text-pine" /> : null}
                </span>
                <span className="flex-1">{b.name}</span>
                {!b.is_current && (
                  <button
                    type="button"
                    aria-label={`Delete branch ${b.name}`}
                    className="ml-2 rounded p-0.5 opacity-60 hover:bg-red-100 hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      handleDelete(b.name);
                    }}
                  >
                    <Trash2 className="size-3 text-red-600" />
                  </button>
                )}
              </DropdownMenuItem>
            ))
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            data-testid="branch-picker-create"
            onSelect={() => handleCreate()}
          >
            <Plus className="size-3.5" />+ Create branch…
          </DropdownMenuItem>

          {nonCurrent.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel data-testid="branch-picker-merge-sub">
                Merge into current
              </DropdownMenuLabel>
              {nonCurrent.map((b) => (
                <DropdownMenuItem
                  key={`merge-${b.name}`}
                  data-testid={`branch-picker-merge-${b.name}`}
                  onSelect={() => props.onMergeRequested?.(b.name)}
                >
                  <GitMerge className="size-3.5" />
                  {b.name}
                </DropdownMenuItem>
              ))}
            </>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem
            data-testid="branch-picker-cherry-pick"
            onSelect={() => props.onCherryPickRequested?.()}
          >
            <CornerUpRight className="size-3.5" />
            Cherry-pick…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {createOpen && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="branch-create-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false);
          }}
        >
          <div
            data-testid="branch-create-dialog"
            className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="branch-create-title" className="mb-3 text-base font-semibold">
              Create new branch
            </h2>
            <input
              data-testid="branch-create-input"
              autoFocus
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  submitCreate();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setCreateOpen(false);
                }
              }}
              placeholder="branch-name"
              className="block w-full rounded border border-stone-300 px-3 py-2 text-sm outline-none focus:border-pine"
            />
            <p className="mt-2 text-xs text-stone-500">
              Creates a branch from the current HEAD and switches to it.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="toolbar"
                size="toolbar"
                type="button"
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </Button>
              <Button
                data-testid="branch-create-submit"
                variant="toolbar-dark"
                size="toolbar"
                type="button"
                disabled={newName.trim().length === 0}
                onClick={() => submitCreate()}
              >
                Create
              </Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
