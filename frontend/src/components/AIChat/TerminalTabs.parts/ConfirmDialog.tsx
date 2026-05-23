/**
 * Modal "Close anyway?" confirmation dialog for TerminalTabs.
 *
 * Extracted in #1413 to keep TerminalTabs under the 150-line function limit.
 */
export interface ConfirmDialogProps {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ message, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      data-testid="terminal-confirm-dialog"
    >
      <div className="w-80 rounded-2xl bg-white p-4 shadow-lg">
        <p className="mb-4 text-sm text-stone-700">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-full border border-stone-300 px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-50"
            onClick={onCancel}
            data-testid="terminal-confirm-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-full bg-red-500 px-3 py-1.5 text-sm text-white hover:bg-red-600"
            onClick={onConfirm}
            data-testid="terminal-confirm-ok"
          >
            Close anyway
          </button>
        </div>
      </div>
    </div>
  );
}
