// ADR-050 §2.2 — floating node action toolbar.
//
// Run / Restart / Delete controls for a canvas block node. Per ADR-050 the
// action buttons float OUTSIDE the square body and only appear on hover or when
// the node is selected. They MUST NOT consume body space or change the node's
// measured geometry, so the toolbar is absolutely positioned above the square
// and is excluded from layout flow.

interface NodeActionToolbarProps {
  /** Show the toolbar (hover or selected). */
  visible: boolean;
  onRun?: () => void;
  onRestart?: () => void;
  onDelete?: () => void;
}

export function NodeActionToolbar({ visible, onRun, onRestart, onDelete }: NodeActionToolbarProps) {
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
        className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-stone-100 hover:text-ink"
        title="Restart block"
        aria-label="Restart block"
        onClick={(event) => {
          event.stopPropagation();
          onRestart?.();
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
          <path d="M13 8a5 5 0 1 1-1.5-3.5M13 3v2.5h-2.5" />
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
    </div>
  );
}
