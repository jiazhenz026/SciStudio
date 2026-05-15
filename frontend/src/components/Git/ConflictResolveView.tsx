/**
 * ADR-039 §3.5a / §6 Phase 3 — Conflict resolution view.
 *
 * D39-2.4b IMPL: per-file status tracking + action wiring. The component
 * lives INSIDE MergeFlow when the merge result is "conflict". Each row
 * shows the file path, an Open-in-editor button, a Mark Resolved button
 * (calls `api.gitMergeStageFile`), and a status badge. Footer has
 * Complete Merge (gated on all-resolved) and Abort Merge.
 *
 * Per-file status is kept local to this component. We could lift it to
 * `gitSlice.mergeInProgress.resolved_files`, but the conflict flow is
 * short-lived (open → resolve → close), so local state is sufficient.
 * If a `git.head_changed` event clears `mergeInProgress`, the parent
 * `MergeFlow` unmounts this component and the state goes with it.
 */
import { useCallback, useMemo, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { api, ApiError } from "../../lib/api";

export interface ConflictResolveViewProps {
  /** Files git left in conflicted state. */
  conflictedFiles: string[];
  /** Focus the file in the main editor tab area. */
  onOpenFile: (path: string) => void;
  /** Wraps `api.gitMergeComplete()` plus optimistic UI update. */
  onResolveAll: () => Promise<void>;
  /** Wraps `api.gitMergeAbort()` plus optimistic UI update. */
  onAbort: () => Promise<void>;
}

type Status = "unresolved" | "resolved";

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message || "Stage failed.";
  if (err instanceof Error) return err.message || "Stage failed.";
  return "Stage failed.";
}

export function ConflictResolveView(
  props: ConflictResolveViewProps,
): JSX.Element {
  const { conflictedFiles, onOpenFile, onResolveAll, onAbort } = props;

  const [statuses, setStatuses] = useState<Record<string, Status>>(() => {
    const init: Record<string, Status> = {};
    for (const f of conflictedFiles) init[f] = "unresolved";
    return init;
  });
  const [stageErrors, setStageErrors] = useState<Record<string, string>>({});
  const [staging, setStaging] = useState<Record<string, boolean>>({});

  const allResolved = useMemo(() => {
    if (conflictedFiles.length === 0) return false;
    return conflictedFiles.every((f) => statuses[f] === "resolved");
  }, [conflictedFiles, statuses]);

  const handleMarkResolved = useCallback(
    async (path: string) => {
      setStaging((s) => ({ ...s, [path]: true }));
      setStageErrors((s) => {
        const { [path]: _drop, ...rest } = s;
        void _drop;
        return rest;
      });
      try {
        await api.gitMergeStageFile(path);
        setStatuses((s) => ({ ...s, [path]: "resolved" }));
      } catch (err) {
        setStageErrors((s) => ({ ...s, [path]: describeError(err) }));
      } finally {
        setStaging((s) => ({ ...s, [path]: false }));
      }
    },
    [],
  );

  if (conflictedFiles.length === 0) {
    return (
      <div
        data-testid="conflict-resolve-view"
        className="flex h-full w-full flex-col gap-2 p-4 text-sm"
      >
        <h2 className="text-base font-semibold">Conflicts in this merge</h2>
        <p className="text-stone-500">No conflicted files.</p>
      </div>
    );
  }

  return (
    <div
      data-testid="conflict-resolve-view"
      className="flex h-full w-full flex-col gap-2 p-2 text-sm"
    >
      <h2 className="text-base font-semibold">Conflicts in this merge</h2>
      <ul role="listbox" className="flex flex-col gap-1">
        {conflictedFiles.map((f) => {
          const status = statuses[f] ?? "unresolved";
          const isStaging = staging[f] === true;
          const stageError = stageErrors[f];
          const badgeId = `conflict-status-${f.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
          return (
            <li
              key={f}
              data-testid={`conflict-row-${f}`}
              data-status={status}
              role="option"
              aria-selected={status === "resolved"}
              className="flex items-center gap-2 rounded bg-stone-50 px-2 py-1.5"
            >
              <code
                data-testid={`conflict-row-path-${f}`}
                className="flex-1 truncate font-mono text-xs"
                title={f}
              >
                {f}
              </code>
              <span
                id={badgeId}
                data-testid={`conflict-status-badge-${f}`}
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  status === "resolved"
                    ? "bg-green-100 text-green-800"
                    : "bg-stone-200 text-stone-700"
                }`}
              >
                {status === "resolved" ? "Resolved" : "Unresolved"}
              </span>
              <Button
                data-testid={`conflict-open-${f}`}
                variant="toolbar"
                size="toolbar"
                type="button"
                onClick={() => onOpenFile(f)}
              >
                Open in editor
              </Button>
              <Button
                data-testid={`conflict-mark-resolved-${f}`}
                variant="toolbar"
                size="toolbar"
                type="button"
                aria-describedby={badgeId}
                disabled={isStaging || status === "resolved"}
                onClick={() => void handleMarkResolved(f)}
              >
                {isStaging ? "Staging…" : "Mark Resolved"}
              </Button>
              {stageError ? (
                <span
                  role="alert"
                  data-testid={`conflict-stage-error-${f}`}
                  className="text-[10px] text-red-700"
                >
                  {stageError}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
      <div className="flex items-center justify-end gap-2 border-t border-stone-200 pt-2">
        <Button
          data-testid="conflict-abort-button"
          variant="toolbar"
          size="toolbar"
          type="button"
          onClick={() => void onAbort()}
        >
          Abort Merge
        </Button>
        <Button
          data-testid="conflict-complete-button"
          variant="toolbar"
          size="toolbar"
          type="button"
          aria-disabled={!allResolved}
          disabled={!allResolved}
          onClick={() => void onResolveAll()}
        >
          Complete Merge
        </Button>
      </div>
    </div>
  );
}

export default ConflictResolveView;
