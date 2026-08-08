// ADR-050 §2.2 — floating node action toolbar.
//
// Run / Delete controls for a canvas block node. Per ADR-050 the
// action buttons float OUTSIDE the square body and only appear on hover or when
// the node is selected. They MUST NOT consume body space or change the node's
// measured geometry, so the toolbar is absolutely positioned above the square
// and is excluded from layout flow.
//
// ADR-053 §6.2 E2 — this is the canvas node's menu, so it is where promotion
// mounts. It arrives as a `trailing` node rather than an `onPromote` callback
// because the shared `PromoteToLibraryAction` decides for itself whether to
// render at all (FR-019, hidden not disabled) and owns the whole flow
// (FR-025); a callback prop would put a second copy of that decision here.

import type { ReactNode } from "react";

//
// ADR-050 Addendum 1 §8.1 (#2033): the toolbar used to carry a third button,
// "Restart block", between run and delete. Its handler was byte-identical to
// run's — same `executeFrom` call, same arguments — so the two buttons offered
// one behaviour behind two icons and two tooltips. The duplicate is gone.

interface NodeActionToolbarProps {
  /** Show the toolbar (hover or selected). */
  visible: boolean;
  onRun?: () => void;
  onDelete?: () => void;
  /** ADR-053 §6.2 E2 — extra controls appended after Delete. */
  trailing?: ReactNode;
}

export function NodeActionToolbar({ visible, onRun, onDelete, trailing }: NodeActionToolbarProps) {
  return (
    <div
      data-testid="node-action-toolbar"
      // Absolute, above the square, centred. `pointer-events` toggles with
      // visibility so a hidden toolbar never intercepts clicks. Opacity (not
      // mount/unmount) keeps geometry measurement stable across states.
      className={`absolute -top-9 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-lg border border-stone-200 bg-white px-1 py-1 shadow-panel transition-opacity ${
        visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
      aria-hidden={!visible}
    >
      <button
        type="button"
        className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-stone-100 hover:text-ink"
        title="Run block"
        aria-label="Run block"
        onClick={(event) => {
          event.stopPropagation();
          onRun?.();
        }}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M4 2.5v11l9-5.5z" />
        </svg>
      </button>
      <button
        type="button"
        className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-500"
        title="Remove block"
        aria-label="Remove block"
        onClick={(event) => {
          event.stopPropagation();
          onDelete?.();
        }}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      </button>
      {trailing}
    </div>
  );
}
