/**
 * ADR-039 §3.6 — StashApplyDialog.
 *
 * Prompts the user after a restore-on-dirty-tree auto-stash. The three
 * actions (Apply now / Keep stashed / Discard) map to gitSlice operations.
 * Per ADR §3.6 the wording is part of the contract.
 */
import { useCallback, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";

export interface StashApplyDialogProps {
  open: boolean;
  stashId: string;
  onClose: () => void;
  onApplyNow?: (stashId: string) => Promise<void>;
  onKeepStashed?: () => void;
  onDiscard?: (stashId: string) => Promise<void>;
}

export function StashApplyDialog(props: StashApplyDialogProps): JSX.Element | null {
  const { open, stashId, onClose, onApplyNow, onKeepStashed, onDiscard } = props;
  const loadStatus = useAppStore((s) => s.loadStatus);
  const setLastError = useAppStore((s) => s.setLastError);
  const [submitting, setSubmitting] = useState(false);

  const defaultApplyNow = useCallback(
    async (sid: string) => {
      await api.gitStashApply(sid);
      void loadStatus();
    },
    [loadStatus],
  );

  const defaultDiscard = useCallback(
    async (sid: string) => {
      await api.gitStashDrop(sid);
    },
    [],
  );

  const handleApply = useCallback(async () => {
    setSubmitting(true);
    try {
      await (onApplyNow ?? defaultApplyNow)(stashId);
      onClose();
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Stash apply failed");
    } finally {
      setSubmitting(false);
    }
  }, [defaultApplyNow, onApplyNow, onClose, setLastError, stashId]);

  const handleDiscard = useCallback(async () => {
    const confirmed = window.confirm("This permanently drops the stash. Continue?");
    if (!confirmed) return;
    setSubmitting(true);
    try {
      await (onDiscard ?? defaultDiscard)(stashId);
      onClose();
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Stash drop failed");
    } finally {
      setSubmitting(false);
    }
  }, [defaultDiscard, onClose, onDiscard, setLastError, stashId]);

  const handleKeep = useCallback(() => {
    if (onKeepStashed) onKeepStashed();
    else onClose();
  }, [onClose, onKeepStashed]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="stash-apply-title"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          handleKeep();
        } else if (e.key === "Enter") {
          e.preventDefault();
          void handleApply();
        }
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) handleKeep();
      }}
    >
      <div
        data-testid="stash-apply-dialog"
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="stash-apply-title" className="text-base font-semibold text-ink">
          Your unsaved changes are stashed.
        </h2>
        <p
          data-testid="stash-apply-dialog-body"
          className="mt-2 text-sm text-stone-600"
        >
          The restore put your previous edits into stash {stashId}. Apply them on top of the restored version?
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button
            data-testid="stash-apply-discard"
            variant="toolbar"
            size="toolbar"
            type="button"
            disabled={submitting}
            onClick={() => void handleDiscard()}
            className="!text-red-700"
          >
            Discard
          </Button>
          <Button
            data-testid="stash-apply-keep"
            variant="toolbar"
            size="toolbar"
            type="button"
            disabled={submitting}
            onClick={handleKeep}
          >
            Keep stashed
          </Button>
          <Button
            data-testid="stash-apply-now"
            variant="toolbar-dark"
            size="toolbar"
            type="button"
            disabled={submitting}
            onClick={() => void handleApply()}
            autoFocus
          >
            Apply now
          </Button>
        </div>
      </div>
    </div>
  );
}
