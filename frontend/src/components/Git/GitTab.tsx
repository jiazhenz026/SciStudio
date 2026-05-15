/**
 * ADR-039 §3.5 — Git BottomPanel tab.
 *
 * Container that composes every Git affordance into a single bottom-panel
 * tab. Previously the Git surface was wired into the top Toolbar (D39-2.3b),
 * which overflowed the viewport on narrow screens and — critically — never
 * mounted `GitHistoryList`, so the commit history + branch graph were
 * unreachable from the production UI. This component restores access to
 * the full feature set (#972).
 *
 * Layout:
 *   - Sticky top bar: BranchPicker · GitStatusBadge · Commit · Stashes.
 *   - Main area: GitHistoryList (which internally toggles List ↔ Graph).
 *   - Modals scoped to the tab: CommitDialog, StashListPanel, MergeFlow
 *     (which itself renders ConflictResolveView when a merge conflicts).
 *
 * Empty-state when no project is open — `gitSlice` no-ops without a
 * project, so we render a hint rather than a dead UI.
 */
import { Archive, GitCommit } from "lucide-react";
import { useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { useAppStore } from "../../store";
import { BranchPicker } from "./BranchPicker";
import { CommitDialog } from "./CommitDialog";
import { GitHistoryList } from "./GitHistoryList";
import { GitStatusBadge } from "./GitStatusBadge";
import { MergeFlow } from "./MergeFlow";
import { StashListPanel } from "./StashListPanel";

export function GitTab(): JSX.Element {
  const currentProject = useAppStore((s) => s.currentProject);
  const openFileTab = useAppStore((s) => s.openFileTab);

  // ADR-039 §3.5 — local UI state for the dialog/drawer triggers. Kept
  // local to this component (rather than in gitSlice) because every
  // surface is short-lived and tab-scoped: unmounting the Git tab tears
  // down the modal state automatically.
  const [commitOpen, setCommitOpen] = useState(false);
  const [stashOpen, setStashOpen] = useState(false);
  // ADR-039 §3.5a / D39-2.4b — merge flow modal. `mergeSource` is the
  // branch the user wants to merge INTO the current branch.
  const [mergeSource, setMergeSource] = useState<string | null>(null);

  if (!currentProject) {
    return (
      <div
        data-testid="git-tab-empty"
        className="flex h-full items-center justify-center"
      >
        <p className="text-sm text-stone-500">
          Open a project to use Git versioning.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="git-tab"
      className="flex h-full min-h-0 flex-col"
    >
      {/* Sticky top bar. Mirrors the previous Toolbar group but lives
          inside the Git tab so the main Toolbar can stay compact. */}
      <div
        data-testid="git-tab-top-bar"
        className="flex shrink-0 items-center gap-2 border-b border-stone-200 bg-white/70 px-3 py-2"
      >
        <BranchPicker
          onMergeRequested={(sourceBranch) => setMergeSource(sourceBranch)}
        />
        <GitStatusBadge onClick={() => setCommitOpen(true)} />
        <Button
          data-testid="git-tab-commit-button"
          variant="toolbar"
          size="toolbar"
          type="button"
          onClick={() => setCommitOpen(true)}
        >
          <GitCommit className="size-3.5" />
          Commit
        </Button>
        <Button
          data-testid="git-tab-stashes-button"
          variant="toolbar"
          size="toolbar"
          type="button"
          onClick={() => setStashOpen(true)}
        >
          <Archive className="size-3.5" />
          Stashes
        </Button>
      </div>

      {/* Main area: commit history with List/Graph toggle. Wrapper has
          min-h-0 so the inner list's overflow-y-auto actually scrolls. */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <GitHistoryList />
      </div>

      {/* Modals scoped to the tab. Kept here so they un-mount with the
          Git tab; they were previously rendered at the Toolbar level. */}
      <CommitDialog open={commitOpen} onClose={() => setCommitOpen(false)} />
      <StashListPanel open={stashOpen} onClose={() => setStashOpen(false)} />
      <MergeFlow
        sourceBranch={mergeSource ?? ""}
        isOpen={mergeSource !== null}
        onClose={() => setMergeSource(null)}
        onOpenFile={(path) => {
          // Open conflicted file in a Monaco file tab so the user can
          // resolve markers inline. Matches the original Toolbar wiring
          // added in PR #952 (Codex P2 follow-up).
          openFileTab(path);
        }}
      />
    </div>
  );
}

export default GitTab;
