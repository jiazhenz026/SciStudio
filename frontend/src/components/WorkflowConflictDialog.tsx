import type { VersionConflictState, WorkflowConflictResolution } from "../store/types";

/**
 * Canvas version-conflict dialog (#1891).
 *
 * The workflow file save is last-write-wins (ADR-039 §5.2). When an external
 * writer — most commonly the AI agent's ``write_workflow`` — modifies the open
 * workflow while the canvas has unsaved local edits, ADR-045 reconciliation
 * detects the conflict and freezes autosave. Without a resolution step the
 * debounced autosave would silently clobber the agent's write.
 *
 * This is the VS Code "the file has changed on disk" prompt, adapted for an
 * autosave editor: instead of asking at save time, we ask the moment the
 * conflict is detected and make the user choose a side. Clean-state remote
 * changes auto-reload and never reach this dialog.
 */
function describeSource(source: VersionConflictState["source"]): string {
  switch (source) {
    case "agent":
      return "the AI agent";
    case "gitRestore":
      return "a git restore";
    case "import":
      return "an import";
    case "external":
      return "an external edit";
    default:
      return "another writer";
  }
}

export function WorkflowConflictDialog({
  conflict,
  onResolve,
}: {
  conflict: VersionConflictState | null;
  onResolve: (resolution: WorkflowConflictResolution) => void;
}) {
  if (!conflict || conflict.entityClass !== "workflow") return null;

  const who = describeSource(conflict.source);
  // ``loadRemote`` discards local edits in favour of the remote version. When
  // there is no remote payload (deleted/moved on disk, or the refetch failed)
  // that resolution clears the canvas, so spell that out.
  const remoteAvailable = Boolean(conflict.remoteWorkflow);
  const loadLabel = remoteAvailable ? "Load their version" : "Discard my edits";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="workflow-conflict-title"
        className="w-full max-w-md rounded-[1.5rem] border border-stone-200 bg-stone-50 p-6 shadow-panel"
        data-testid="workflow-conflict-dialog"
      >
        <h2 id="workflow-conflict-title" className="font-display text-2xl text-ink">
          Workflow changed elsewhere
        </h2>

        <p className="mt-4 text-sm text-stone-700">
          This workflow was modified by {who} while you had unsaved changes. Choose which version to
          keep — saving yours will overwrite theirs.
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm transition hover:border-ink"
            onClick={() => onResolve("loadRemote")}
            type="button"
            data-testid="workflow-conflict-load-remote"
          >
            {loadLabel}
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine"
            onClick={() => onResolve("keepLocal")}
            type="button"
            data-testid="workflow-conflict-keep-local"
          >
            Keep my version
          </button>
        </div>
      </div>
    </div>
  );
}
