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
}

export function useFlowCallbacks(opts: FlowCallbacksOpts) {
  const { onRunBlock, onRestartBlock, onDeleteNode, onErrorClick, onUpdateNodeConfig } = opts;
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
  const makeOnUpdateConfig = useCallback(
    (nodeId: string) => (patch: Record<string, unknown>) => onUpdateNodeConfig(nodeId, patch),
    [onUpdateNodeConfig],
  );
  return { makeOnRun, makeOnRestart, makeOnDelete, makeOnErrorClick, makeOnUpdateConfig };
}
