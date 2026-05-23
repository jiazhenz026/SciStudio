/**
 * Merge state machine extracted from MergeFlow (#1413).
 *
 *   IDLE → IN_FLIGHT → SUCCESS | CONFLICT | ERROR
 *   CONFLICT → COMPLETING → SUCCESS
 *   CONFLICT → ABORTING → (closed)
 */
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../../../lib/api";
import { useAppStore } from "../../../store";

export type MergePhase =
  | "idle"
  | "in_flight"
  | "conflict"
  | "completing"
  | "aborting"
  | "success"
  | "error";

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message || "Merge failed.";
  if (err instanceof Error) return err.message || "Merge failed.";
  return "Merge failed.";
}

export interface UseMergeStateMachineOpts {
  sourceBranch: string;
  isOpen: boolean;
  onClose: () => void;
}

export interface MergeStateMachine {
  phase: MergePhase;
  conflictedFiles: string[];
  error: string | null;
  successMessage: string | null;
  handleComplete: () => Promise<void>;
  handleAbort: () => Promise<void>;
  handleRequestClose: () => void;
}

function isClosingLocked(phase: MergePhase): boolean {
  return (
    phase === "in_flight" || phase === "conflict" || phase === "completing" || phase === "aborting"
  );
}

export function useMergeStateMachine(opts: UseMergeStateMachineOpts): MergeStateMachine {
  const { sourceBranch, isOpen, onClose } = opts;
  const currentBranch = useAppStore((s) => s.currentBranch);
  const setMergeInProgress = useAppStore((s) => s.setMergeInProgress);
  const invalidateHistory = useAppStore((s) => s.invalidateHistory);
  const loadLog = useAppStore((s) => s.loadLog);
  const loadStatus = useAppStore((s) => s.loadStatus);

  const [phase, setPhase] = useState<MergePhase>("idle");
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

  const markSuccess = useCallback(
    (message: string) => {
      setSuccessMessage(message);
      setPhase("success");
      setMergeInProgress(null);
      invalidateHistory();
      void loadStatus();
      void loadLog();
    },
    [setMergeInProgress, invalidateHistory, loadLog, loadStatus],
  );

  const handleConflictResult = useCallback(
    (files: string[]) => {
      if (files.length === 0) {
        // Defensive: conflict result with no files; treat as clean.
        markSuccess(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
        return;
      }
      setConflictedFiles(files);
      setMergeInProgress({ source_branch: sourceBranch, conflicted_files: files });
      setPhase("conflict");
    },
    [sourceBranch, currentBranch, markSuccess, setMergeInProgress],
  );

  const runMerge = useCallback(async () => {
    if (!sourceBranch) return;
    setPhase("in_flight");
    setError(null);
    try {
      const result = await api.gitMerge(sourceBranch);
      if (result.result === "fast-forward") {
        markSuccess(`Fast-forwarded ${currentBranch ?? "current"} to ${sourceBranch}.`);
      } else if (result.result === "clean") {
        markSuccess(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
      } else if (result.result === "conflict") {
        handleConflictResult(result.conflicted_files ?? []);
      }
    } catch (err) {
      setError(describeError(err));
      setPhase("error");
    }
  }, [sourceBranch, currentBranch, markSuccess, handleConflictResult]);

  // Kick off the merge when the modal opens.
  useEffect(() => {
    if (!isOpen) return;
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
      markSuccess(`Merged ${sourceBranch} into ${currentBranch ?? "current"}.`);
    } catch (err) {
      setError(describeError(err));
      setPhase("conflict");
    }
  }, [sourceBranch, currentBranch, markSuccess]);

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
    if (isClosingLocked(phase)) return;
    onClose();
  }, [phase, onClose]);

  return {
    phase,
    conflictedFiles,
    error,
    successMessage,
    handleComplete,
    handleAbort,
    handleRequestClose,
  };
}

export const isMergeClosingLocked = isClosingLocked;
