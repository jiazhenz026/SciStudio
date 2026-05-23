/**
 * ADR-039 §3.5a / §3.7 / §6 Phase 3 — Merge flow orchestrator.
 *
 * D39-2.4b IMPL: full state machine wiring `gitMerge` → fast-forward /
 * clean / conflict / error states, with conflict resolution delegated to
 * `ConflictResolveView` and finalized via `gitMergeComplete` /
 * `gitMergeAbort`.
 *
 * State machine:
 *
 *   IDLE → IN_FLIGHT (POST /api/git/merge)
 *     ├─ fast-forward / clean → SUCCESS → 1s toast → CLOSE
 *     ├─ conflict             → CONFLICT (renders ConflictResolveView)
 *     │                          ├─ Complete → COMPLETING → SUCCESS
 *     │                          └─ Abort    → ABORTING   → CLOSE
 *     └─ error                → ERROR (user dismisses)
 *
 * Closing the modal during CONFLICT is blocked — the conflicted working
 * tree would be orphaned. The user must either Complete or Abort.
 */
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { useAppStore } from "../../store";

import { MergeFlowBody } from "./MergeFlow.parts/MergeFlowBody";
import { isMergeClosingLocked, useMergeStateMachine } from "./MergeFlow.parts/useMergeStateMachine";

export interface MergeFlowProps {
  /** Branch the user wants to merge INTO the current branch. */
  sourceBranch: string;
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Caller-supplied close handler. The modal also closes itself on success. */
  onClose: () => void;
  /**
   * Optional: focus a file in the main editor tab area. Called by
   * `ConflictResolveView` when the user clicks "Open in editor".
   */
  onOpenFile?: (path: string) => void;
}

export function MergeFlow(props: MergeFlowProps): JSX.Element | null {
  const { sourceBranch, isOpen, onClose, onOpenFile } = props;

  const currentBranch = useAppStore((s) => s.currentBranch);

  const machine = useMergeStateMachine({ sourceBranch, isOpen, onClose });

  if (!isOpen) return null;

  const titleText = `Merge ${sourceBranch} into ${currentBranch ?? "current"}`;
  const closeLocked = isMergeClosingLocked(machine.phase);

  return (
    <div
      data-testid="merge-flow"
      role="dialog"
      aria-modal="true"
      aria-label={titleText}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) machine.handleRequestClose();
      }}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
          <h2 className="text-base font-semibold text-ink">{titleText}</h2>
          <Button
            data-testid="merge-flow-close"
            variant="toolbar"
            size="toolbar"
            type="button"
            disabled={closeLocked}
            onClick={machine.handleRequestClose}
          >
            Close
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          <MergeFlowBody
            phase={machine.phase}
            sourceBranch={sourceBranch}
            currentBranch={currentBranch}
            conflictedFiles={machine.conflictedFiles}
            error={machine.error}
            successMessage={machine.successMessage}
            onOpenFile={onOpenFile}
            onComplete={machine.handleComplete}
            onAbort={machine.handleAbort}
            onClose={onClose}
          />
        </div>
      </div>
    </div>
  );
}

export default MergeFlow;
