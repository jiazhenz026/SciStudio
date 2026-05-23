/**
 * Phase-driven body of MergeFlow. Extracted in #1413 to keep MergeFlow's
 * top-level function under the 150-line / complexity-15 limit.
 */
import { Button } from "@/components/ui/button";

import { ConflictResolveView } from "../ConflictResolveView";
import type { MergePhase } from "./useMergeStateMachine";

export interface MergeFlowBodyProps {
  phase: MergePhase;
  sourceBranch: string;
  currentBranch: string | null;
  conflictedFiles: string[];
  error: string | null;
  successMessage: string | null;
  onOpenFile?: (path: string) => void;
  onComplete: () => Promise<void>;
  onAbort: () => Promise<void>;
  onClose: () => void;
}

function InFlight({
  sourceBranch,
  currentBranch,
}: {
  sourceBranch: string;
  currentBranch: string | null;
}) {
  return (
    <div
      data-testid="merge-flow-in-flight"
      className="flex items-center justify-center p-6 text-sm text-stone-500"
    >
      Merging {sourceBranch} into {currentBranch ?? "current"}…
    </div>
  );
}

function ConflictBody({
  phase,
  conflictedFiles,
  error,
  onOpenFile,
  onComplete,
  onAbort,
}: {
  phase: MergePhase;
  conflictedFiles: string[];
  error: string | null;
  onOpenFile?: (path: string) => void;
  onComplete: () => Promise<void>;
  onAbort: () => Promise<void>;
}) {
  return (
    <div data-testid="merge-flow-conflict" className="flex h-full flex-col">
      <p className="border-b border-stone-200 pb-2 text-sm text-stone-700">
        {conflictedFiles.length} files have conflicts. Resolve each, then click Complete Merge.
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
        onResolveAll={onComplete}
        onAbort={onAbort}
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
  );
}

function SuccessBody({ message }: { message: string | null }) {
  return (
    <div data-testid="merge-flow-success" className="p-4 text-sm text-green-700">
      {message ?? "Merge succeeded."}
    </div>
  );
}

function ErrorBody({ error, onClose }: { error: string | null; onClose: () => void }) {
  return (
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
        onClick={onClose}
      >
        OK
      </Button>
    </div>
  );
}

export function MergeFlowBody(props: MergeFlowBodyProps) {
  const { phase } = props;
  if (phase === "idle" || phase === "in_flight") {
    return <InFlight sourceBranch={props.sourceBranch} currentBranch={props.currentBranch} />;
  }
  if (phase === "conflict" || phase === "completing" || phase === "aborting") {
    return (
      <ConflictBody
        phase={phase}
        conflictedFiles={props.conflictedFiles}
        error={props.error}
        onOpenFile={props.onOpenFile}
        onComplete={props.onComplete}
        onAbort={props.onAbort}
      />
    );
  }
  if (phase === "success") {
    return <SuccessBody message={props.successMessage} />;
  }
  if (phase === "error") {
    return <ErrorBody error={props.error} onClose={props.onClose} />;
  }
  return null;
}
