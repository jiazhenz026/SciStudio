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
 *   - Sticky top bar: BranchPicker · GitStatusBadge · Commit.
 *   - Main area: GitHistoryList (which internally toggles List ↔ Graph).
 *   - Tab-scoped modals: CommitDialog.
 *
 * MergeFlow is intentionally NOT rendered here — see Codex P1 on PR #974.
 * Switching away from the Git tab would otherwise unmount it mid-conflict-
 * resolution and bypass its "cannot close during conflict" guard, leaving
 * the repository in a half-merged state with no visible recovery UI. The
 * modal lives at the BottomPanel level instead (`<MergeFlow>` mounted
 * unconditionally there) and is driven by `gitSlice.mergeFlowSource` so
 * it survives every tab switch.
 *
 * Empty-state when no project is open — `gitSlice` no-ops without a
 * project, so we render a hint rather than a dead UI.
 */
import { GitCommit } from "lucide-react";
import { useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { useAppStore } from "../../store";
import { BranchPicker } from "./BranchPicker";
import { CommitDialog } from "./CommitDialog";
import { GitHistoryList } from "./GitHistoryList";
import { GitStatusBadge } from "./GitStatusBadge";

export function GitTab(): JSX.Element {
  const currentProject = useAppStore((s) => s.currentProject);
  // #972 (Codex P1 on PR #974) — drive MergeFlow via slice so it stays
  // mounted at the BottomPanel level. Keep CommitDialog local: its
  // close guard is not load-bearing (the user can always reopen),
  // and tab-scoping keeps the slice surface tight.
  const setMergeFlowSource = useAppStore((s) => s.setMergeFlowSource);

  const [commitOpen, setCommitOpen] = useState(false);

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
          onMergeRequested={(sourceBranch) =>
            setMergeFlowSource(sourceBranch, currentProject.id)
          }
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
      </div>

      {/* Main area: commit history with List/Graph toggle. Wrapper has
          min-h-0 so the inner list's overflow-y-auto actually scrolls. */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <GitHistoryList />
      </div>

      {/* Tab-scoped modals only. MergeFlow is mounted at the BottomPanel
          level (driven by `gitSlice.mergeFlowSource`) so it survives a
          bottom-tab switch during conflict resolution — see Codex P1 on
          PR #974 and the file-top docstring. */}
      <CommitDialog open={commitOpen} onClose={() => setCommitOpen(false)} />
    </div>
  );
}

export default GitTab;
