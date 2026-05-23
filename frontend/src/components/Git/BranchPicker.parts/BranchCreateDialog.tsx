/**
 * Inline create-branch dialog for BranchPicker. Extracted in #1413.
 */
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";

export interface BranchCreateDialogProps {
  newName: string;
  onChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export function BranchCreateDialog({
  newName,
  onChange,
  onCancel,
  onSubmit,
}: BranchCreateDialogProps) {
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="branch-create-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        data-testid="branch-create-dialog"
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="branch-create-title" className="mb-3 text-base font-semibold">
          Create new branch
        </h2>
        <input
          data-testid="branch-create-input"
          autoFocus
          type="text"
          value={newName}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onCancel();
            }
          }}
          placeholder="branch-name"
          className="block w-full rounded border border-stone-300 px-3 py-2 text-sm outline-none focus:border-pine"
        />
        <p className="mt-2 text-xs text-stone-500">
          Creates a branch from the current HEAD and switches to it.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="toolbar" size="toolbar" type="button" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            data-testid="branch-create-submit"
            variant="toolbar-dark"
            size="toolbar"
            type="button"
            disabled={newName.trim().length === 0}
            onClick={onSubmit}
          >
            Create
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
