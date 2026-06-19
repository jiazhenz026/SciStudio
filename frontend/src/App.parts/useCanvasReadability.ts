// ADR-050 §3 — canvas readability wiring (focus mode + tidy layout).
//
// Extracted from App.tsx (which is at its `max-lines-per-function` cap)
// following the same one-concern-per-hook pattern as `useBottomPanelControls`
// and `useCanvasHandlers`. Owns the focus-mode UI state selectors and the
// batch layout action, exposed as a single `CanvasReadabilityWiring` object so
// App.tsx passes one prop into ProjectWorkspace.
//
// Focus mode is frontend-only view state (FR-018); tidy writes ONLY
// `node.layout` through `updateNodeLayoutBatch` (FR-022/FR-024). Neither path
// is implemented here — this hook only wires the store into the canvas.
import { useMemo } from "react";

import type { CanvasReadabilityWiring } from "./ProjectWorkspace";
import { useAppStore } from "../store";

/**
 * @param onWarningClick App-level handler that selects a node and opens the
 *   BottomPanel Config detail (ADR-050 FR-013). Supplied by App.tsx from
 *   `useBottomPanelControls.handleNodeSelect`.
 */
export function useCanvasReadability(
  onWarningClick: (blockId: string) => void,
): CanvasReadabilityWiring {
  const focusMode = useAppStore((state) => state.focusMode);
  const enterFocusMode = useAppStore((state) => state.enterFocusMode);
  const exitFocusMode = useAppStore((state) => state.exitFocusMode);
  const updateNodeLayoutBatch = useAppStore((state) => state.updateNodeLayoutBatch);

  return useMemo<CanvasReadabilityWiring>(
    () => ({
      focusMode,
      onWarningClick,
      onEnterFocusMode: enterFocusMode,
      onExitFocusMode: exitFocusMode,
      onTidyLayout: updateNodeLayoutBatch,
    }),
    [focusMode, onWarningClick, enterFocusMode, exitFocusMode, updateNodeLayoutBatch],
  );
}
