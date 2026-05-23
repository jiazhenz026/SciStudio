/**
 * Toast surfaced after a safe dirty-tree branch switch (ADR-039 Addendum 1).
 *
 * Extracted in #1413 from BranchPicker.tsx so the main component stays small.
 */
import { createPortal } from "react-dom";

export interface AutoCommitToastProps {
  message: string;
}

export function AutoCommitToast({ message }: AutoCommitToastProps) {
  return createPortal(
    <div
      data-testid="branch-picker-auto-commit-toast"
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 max-w-md rounded-md border border-stone-300 bg-white px-4 py-3 text-xs text-ink shadow-lg"
    >
      {message}
    </div>,
    document.body,
  );
}
