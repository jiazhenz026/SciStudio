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
import { ChevronDown, GitBranch as GitBranchIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

import { useAppStore } from "../../store";
import { AutoCommitToast } from "./BranchPicker.parts/AutoCommitToast";
import { BranchCreateDialog } from "./BranchPicker.parts/BranchCreateDialog";
import { BranchMenuContent } from "./BranchPicker.parts/BranchMenuContent";

export interface BranchPickerProps {
  onMergeRequested?: (sourceBranch: string) => void;
  onCherryPickRequested?: () => void;
  onCreateBranchRequested?: () => void;
}

/**
 * ADR-039 Addendum 1 (#1354) — auto-commit toast hook.
 *
 * Mirrors `lastNotice` into a local timer so multiple consumers of
 * `lastNotice` (RestoreWorkflowButton's hint slot is a sibling reader)
 * don't fight over a single global clear.
 */
function useAutoCommitToast(): string | null {
  const lastNotice = useAppStore((s) => s.lastNotice);
  const setLastNotice = useAppStore((s) => s.setLastNotice);
  const [autoCommitToast, setAutoCommitToast] = useState<string | null>(null);

  useEffect(() => {
    if (!lastNotice) {
      setAutoCommitToast(null);
      return;
    }
    // Only render the toast here if the notice actually came from a
    // branch switch (heuristic: "before switching"); the restore path
    // surfaces its own hint inline in RunDetail.
    if (lastNotice.includes("before switching")) {
      setAutoCommitToast(lastNotice);
      const handle = window.setTimeout(() => {
        setAutoCommitToast(null);
        setLastNotice(null);
      }, 6000);
      return () => window.clearTimeout(handle);
    }
    return;
  }, [lastNotice, setLastNotice]);

  return autoCommitToast;
}

export function BranchPicker(props: BranchPickerProps): JSX.Element {
  const branches = useAppStore((s) => s.branches);
  const currentBranch = useAppStore((s) => s.currentBranch);
  const loadBranches = useAppStore((s) => s.loadBranches);
  const switchBranch = useAppStore((s) => s.switchBranch);
  const createBranch = useAppStore((s) => s.createBranch);
  const deleteBranch = useAppStore((s) => s.deleteBranch);
  const currentProject = useAppStore((s) => s.currentProject);
  const autoCommitToast = useAutoCommitToast();

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
        console.warn("[BranchPicker] createBranch failed:", err);
      })
      .finally(() => {
        setCreateOpen(false);
        setNewName("");
      });
  }, [createBranch, newName, switchBranch]);

  const handleDelete = useCallback(
    (name: string) => {
      const confirmed = window.confirm(`Delete branch '${name}'? This cannot be undone.`);
      if (!confirmed) return;
      void deleteBranch(name).catch((err) => {
        console.warn("[BranchPicker] deleteBranch failed:", err);
      });
    },
    [deleteBranch],
  );

  const triggerLabel = currentBranch ?? (branches === null ? "loading…" : "no branch");

  // #984 Option A fix: re-fetch on dropdown open when the cache is null.
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
        <BranchMenuContent
          branches={branches}
          onSwitch={handleSwitch}
          onDelete={handleDelete}
          onCreate={handleCreate}
          onMergeRequested={props.onMergeRequested}
          onCherryPickRequested={props.onCherryPickRequested}
        />
      </DropdownMenu>

      {autoCommitToast && <AutoCommitToast message={autoCommitToast} />}

      {createOpen && (
        <BranchCreateDialog
          newName={newName}
          onChange={setNewName}
          onCancel={() => setCreateOpen(false)}
          onSubmit={submitCreate}
        />
      )}
    </>
  );
}
