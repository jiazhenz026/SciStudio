/**
 * Memoised per-node callback factories for WorkflowCanvas. Extracted in
 * #1413 / #1414 so the main component stays under the 150-line limit.
 */
import { useCallback } from "react";

export interface FlowCallbacksOpts {
  onRunBlock: (blockId: string) => void;
  onRestartBlock: (blockId: string) => void;
  onDeleteNode: (nodeId: string) => void;
  onErrorClick: (blockId: string) => void;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
  /**
   * ADR-050 FR-013 — warning-status click handler. Selects the node and opens
   * the BottomPanel Config detail. Optional so existing call sites compile
   * before FE-1 wires `onWarningClick` into the node status surface.
   */
  onWarningClick?: (blockId: string) => void;
}

export function useFlowCallbacks(opts: FlowCallbacksOpts) {
  const {
    onRunBlock,
    onRestartBlock,
    onDeleteNode,
    onErrorClick,
    onUpdateNodeConfig,
    onWarningClick,
  } = opts;
  const makeOnRun = useCallback((nodeId: string) => () => onRunBlock(nodeId), [onRunBlock]);
  const makeOnRestart = useCallback(
    (nodeId: string) => () => onRestartBlock(nodeId),
    [onRestartBlock],
  );
  const makeOnDelete = useCallback((nodeId: string) => () => onDeleteNode(nodeId), [onDeleteNode]);
  const makeOnErrorClick = useCallback(
    (nodeId: string) => () => onErrorClick(nodeId),
    [onErrorClick],
  );
  // ADR-050 FR-013 — route the warning status to ConfigPanel via the App-level
  // handler. When no handler is provided the factory returns `undefined` so
  // `BlockNodeData.onWarningClick` stays optional.
  const makeOnWarningClick = useCallback(
    (nodeId: string): (() => void) | undefined =>
      onWarningClick ? () => onWarningClick(nodeId) : undefined,
    [onWarningClick],
  );
  const makeOnUpdateConfig = useCallback(
    (nodeId: string) => (patch: Record<string, unknown>) => onUpdateNodeConfig(nodeId, patch),
    [onUpdateNodeConfig],
  );
  return {
    makeOnRun,
    makeOnRestart,
    makeOnDelete,
    makeOnErrorClick,
    makeOnWarningClick,
    makeOnUpdateConfig,
  };
}
