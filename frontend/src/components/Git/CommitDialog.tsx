/**
 * ADR-039 §3.5 — CommitDialog.
 *
 * Modal that the user opens via the toolbar "Commit" button. Renders a
 * multi-line message editor pre-filled with a template that includes the
 * list of modified files (from `GET /api/git/status`), then POSTs to
 * `/api/git/commit` via `gitSlice.commit(...)` and closes on success.
 *
 * Implementation notes (D39-2.3b):
 *   - No external Dialog primitive is registered yet; we use a fixed-
 *     position overlay with a centered card. The same pattern already
 *     ships in DataRouterModal.tsx.
 *   - All `data-testid` attributes match the contract in the top-of-file
 *     docstring; vitest tests below assert against them.
 *
 * See the original SKELETON header for the full contract — copy strings,
 * keyboard shortcuts, edge cases, accessibility — re-stated below in code.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { JSX, KeyboardEvent as ReactKeyboardEvent } from "react";

import { Button } from "@/components/ui/button";

import { ApiError } from "../../lib/api";
import { useAppStore } from "../../store";
import type { GitStatus } from "../../types/api";
import { WorkingTreeList } from "./CommitDialog.parts/WorkingTreeList";

export interface CommitDialogProps {
  open: boolean;
  onClose: () => void;
  initialFiles?: string[];
  defaultAuthor?: string;
  onCommitSuccess?: (sha: string) => void;
}

/** Default commit-message template per ADR §3.5 line 230. */
export const COMMIT_TEMPLATE = `<one-line subject>

# What changed:
# - workflows/<id>.yaml: …
# - blocks/<file>.py:    …
`;

/** Strip git-style comment lines (those starting with "#"); trim whitespace. */
export function stripCommentLines(message: string): string {
  return message
    .split("\n")
    .filter((line) => !line.startsWith("#"))
    .join("\n")
    .trim();
}

/** Render an auto-detected files block (read-only, comment-prefixed). */
export function formatAutoDetectedFiles(status: GitStatus | null): string {
  if (!status) return "";
  const lines: string[] = ["# Auto-detected modified files:"];
  for (const f of status.modified) lines.push(`#   M  ${f}`);
  for (const f of status.staged) lines.push(`#   S  ${f}`);
  for (const f of status.untracked) lines.push(`#   A  ${f}`);
  return lines.join("\n");
}

export function CommitDialog(props: CommitDialogProps): JSX.Element | null {
  const { open, onClose, initialFiles, onCommitSuccess } = props;

  const status = useAppStore((s) => s.status);
  const loadStatus = useAppStore((s) => s.loadStatus);
  const commit = useAppStore((s) => s.commit);

  const [message, setMessage] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Refresh status whenever the dialog opens so the file list reflects reality.
  useEffect(() => {
    if (open) {
      void loadStatus();
      setLocalError(null);
    }
  }, [open, loadStatus]);

  const placeholder = useMemo(() => {
    const detected = formatAutoDetectedFiles(status);
    return detected ? `${COMMIT_TEMPLATE}\n${detected}` : COMMIT_TEMPLATE;
  }, [status]);

  const stripped = stripCommentLines(message);
  const isClean = status?.dirty === false;
  const submitDisabled = submitting || stripped.length === 0 || isClean;

  const onSubmit = useCallback(async () => {
    if (submitting) return;
    if (stripped.length === 0) {
      setLocalError("Commit message cannot be empty.");
      return;
    }
    setSubmitting(true);
    setLocalError(null);
    try {
      const sha = await commit(stripped, initialFiles);
      setMessage("");
      onCommitSuccess?.(sha);
      onClose();
    } catch (err) {
      let msg: string;
      if (err instanceof ApiError && err.status === 503) {
        msg = "Git binary not available. Reinitialize from Settings → Git.";
      } else if (err instanceof Error) {
        msg = err.message;
      } else {
        msg = "Commit failed";
      }
      setLocalError(msg);
    } finally {
      setSubmitting(false);
    }
  }, [commit, initialFiles, onClose, onCommitSuccess, stripped, submitting]);

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        void onSubmit();
      }
    },
    [onClose, onSubmit],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="commit-dialog-title"
      onKeyDown={handleKeyDown}
      onClick={(e) => {
        // Click on backdrop closes; clicks inside content are stopped below.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        data-testid="commit-dialog"
        className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="commit-dialog-title" className="mb-3 text-lg font-semibold text-ink">
          Commit changes
        </h2>

        <textarea
          data-testid="commit-dialog-message"
          className="block h-48 w-full resize-none rounded border border-stone-300 p-3 font-mono text-sm outline-none focus:border-pine"
          placeholder={placeholder}
          value={message}
          rows={12}
          onChange={(e) => setMessage(e.target.value)}
          autoFocus
        />

        <WorkingTreeList status={status} />

        {localError && (
          <div
            role="alert"
            aria-live="assertive"
            data-testid="commit-dialog-error"
            className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {localError}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button
            data-testid="commit-dialog-cancel"
            variant="toolbar"
            size="toolbar"
            onClick={onClose}
            type="button"
          >
            Cancel
          </Button>
          <Button
            data-testid="commit-dialog-submit"
            variant="toolbar-dark"
            size="toolbar"
            onClick={() => void onSubmit()}
            disabled={submitDisabled}
            type="button"
          >
            {submitting ? "Committing…" : "Commit"}
          </Button>
        </div>
      </div>
    </div>
  );
}
