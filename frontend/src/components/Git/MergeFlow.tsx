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
 *     │                          ├─ Complete → IN_FLIGHT_COMPLETE → SUCCESS
 *     │                          └─ Abort    → IN_FLIGHT_ABORT    → CLOSE
 *     └─ error                → ERROR (user dismisses)
 *
 * Closing the modal during CONFLICT is blocked — the conflicted working
 * tree would be orphaned. The user must either Complete or Abort.
 */
import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { api, ApiError } from "../../lib/api";
import { useAppStore } from "../../store";

import { ConflictResolveView } from "./ConflictResolveView";

type Phase = "idle" | "in_flight" | "conflict" | "completing" | "aborting" | "success" | "error";

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

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message || "Merge failed.";
  if (err instanceof Error) return err.message || "Merge failed.";
  return "Merge failed.";
}

export function MergeFlow(props: MergeFlowProps): JSX.Element | null {
  const { sourceBranch, isOpen, onClose, onOpenFile } = props;

  const currentBranch = useAppStore((s) => s.currentBranch);
  const setMergeInProgress = useAppStore((s) => s.setMergeInProgress);
  const invalidateHistory = useAppStore((s) => s.invalidateHistory);
  const loadLog = useAppStore((s) => s.loadLog);
  const loadStatus = useAppStore((s) => s.loadStatus);

  const [phase, setPhase] = useState<Phase>("idle");
  const [conflictedFiles, setConflictedFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Reset when the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    setPhase("idle");
    setConflictedFiles([]);
    setError(null);
    setSuccessMessage(null);
  }, [isOpen, sourceBranch]);

  const runMerge = useCallback(async () => {
    if (!sourceBranch) return;
    setPhase("in_flight");
    setError(null);
    try {
      const result = await api.gitMerge(sourceBranch);
      if (result.result === "fast-forward") {
        setSuccessMessage(`Fast-forwarded ${currentBranch ?? "current"} to ${sourceBranch}.`);
        setPhase("success");
        setMergeInProgress(null);
        invalidateHistory();
        void loadStatus();
        void loadLog();
      } else if (result.result === "clean") {
        setSuccessMessage(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
        setPhase("success");
        setMergeInProgress(null);
        invalidateHistory();
        void loadStatus();
        void loadLog();
      } else if (result.result === "conflict") {
        const files = result.conflicted_files ?? [];
        if (files.length === 0) {
          // Defensive: conflict result with no files; treat as clean.
          setSuccessMessage(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
          setPhase("success");
          setMergeInProgress(null);
        } else {
          setConflictedFiles(files);
          setMergeInProgress({
            source_branch: sourceBranch,
            conflicted_files: files,
          });
          setPhase("conflict");
        }
      }
    } catch (err) {
      setError(describeError(err));
      setPhase("error");
    }
  }, [sourceBranch, currentBranch, setMergeInProgress, invalidateHistory, loadLog, loadStatus]);

  // Kick off the merge when the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    // Defer one tick so users can see the in-flight UI; React state
    // updates batch otherwise.
    void runMerge();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Auto-close on SUCCESS after a brief toast.
  useEffect(() => {
    if (phase !== "success") return;
    const t = window.setTimeout(() => {
      onClose();
    }, 1000);
    return () => window.clearTimeout(t);
  }, [phase, onClose]);

  const handleComplete = useCallback(async () => {
    setPhase("completing");
    setError(null);
    try {
      await api.gitMergeComplete();
      setSuccessMessage(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
      setMergeInProgress(null);
      invalidateHistory();
      void loadStatus();
      void loadLog();
      setPhase("success");
    } catch (err) {
      setError(describeError(err));
      setPhase("conflict");
    }
  }, [sourceBranch, currentBranch, setMergeInProgress, invalidateHistory, loadLog, loadStatus]);

  const handleAbort = useCallback(async () => {
    const ok = window.confirm("Discard the in-progress merge? All resolution work will be lost.");
    if (!ok) return;
    setPhase("aborting");
    setError(null);
    try {
      await api.gitMergeAbort();
      setMergeInProgress(null);
      invalidateHistory();
      void loadStatus();
      onClose();
    } catch (err) {
      setError(describeError(err));
      setPhase("conflict");
    }
  }, [setMergeInProgress, invalidateHistory, loadStatus, onClose]);

  // Block close while we're in the conflict / completing / aborting phase.
  const handleRequestClose = useCallback(() => {
    if (
      phase === "in_flight" ||
      phase === "conflict" ||
      phase === "completing" ||
      phase === "aborting"
    ) {
      return; // no-op
    }
    onClose();
  }, [phase, onClose]);

  if (!isOpen) return null;

  const titleText = `Merge ${sourceBranch} into ${currentBranch ?? "current"}`;

  return (
    <div
      data-testid="merge-flow"
      role="dialog"
      aria-modal="true"
      aria-label={titleText}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleRequestClose();
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
            disabled={
              phase === "in_flight" ||
              phase === "conflict" ||
              phase === "completing" ||
              phase === "aborting"
            }
            onClick={handleRequestClose}
          >
            Close
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {phase === "idle" || phase === "in_flight" ? (
            <div
              data-testid="merge-flow-in-flight"
              className="flex items-center justify-center p-6 text-sm text-stone-500"
            >
              Merging {sourceBranch} into {currentBranch ?? "current"}…
            </div>
          ) : phase === "conflict" || phase === "completing" || phase === "aborting" ? (
            <div data-testid="merge-flow-conflict" className="flex h-full flex-col">
              <p className="border-b border-stone-200 pb-2 text-sm text-stone-700">
                {conflictedFiles.length} files have conflicts. Resolve each, then click Complete
                Merge.
              </p>
              {error ? (
                <div
                  role="alert"
                  data-testid="merge-flow-error"
                  className="my-2 rounded border border-red-300 bg-red-50 p-2 text-xs text-red-700"
                >
                  {error}
                </div>
              ) : null}
              <ConflictResolveView
                conflictedFiles={conflictedFiles}
                onOpenFile={(p) => onOpenFile?.(p)}
                onResolveAll={handleComplete}
                onAbort={handleAbort}
              />
              {phase === "completing" ? (
                <p data-testid="merge-flow-completing" className="mt-2 text-xs text-stone-500">
                  Finalizing merge…
                </p>
              ) : null}
              {phase === "aborting" ? (
                <p data-testid="merge-flow-aborting" className="mt-2 text-xs text-stone-500">
                  Aborting merge…
                </p>
              ) : null}
            </div>
          ) : phase === "success" ? (
            <div data-testid="merge-flow-success" className="p-4 text-sm text-green-700">
              {successMessage ?? "Merge succeeded."}
            </div>
          ) : phase === "error" ? (
            <div className="flex flex-col gap-3 p-4">
              <div
                role="alert"
                data-testid="merge-flow-error"
                className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700"
              >
                {error ?? "Merge failed."}
              </div>
              <Button
                data-testid="merge-flow-error-dismiss"
                variant="toolbar"
                size="toolbar"
                type="button"
                onClick={() => onClose()}
              >
                OK
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default MergeFlow;
