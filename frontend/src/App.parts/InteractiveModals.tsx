// Extracted from App.tsx as part of the #1422 god-file split.
//
// InteractiveModals — the DataRouter / PairEditor modals that surface when
// a paused interactive block publishes its prompt on the workflow
// WebSocket. Kept as a small mount that subscribes to the prompt slice so
// it does not need a 2-screen prop drill from App.tsx.

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { useAppStore } from "../store";

import { DataRouterModal } from "../components/DataRouterModal";
import { PairEditorModal } from "../components/PairEditorModal";

export function InteractiveModals() {
  const interactivePrompt = useAppStore((s) => s.interactivePrompt);
  const setInteractivePrompt = useAppStore((s) => s.setInteractivePrompt);
  const workflowId = useAppStore((s) => s.workflowId);

  if (interactivePrompt?.blockType === "DataRouter") {
    return (
      <DataRouterModal
        blockId={interactivePrompt.blockId}
        inputPorts={(interactivePrompt.data.input_ports as string[]) ?? []}
        outputPorts={(interactivePrompt.data.output_ports as string[]) ?? []}
        itemsPerPort={
          (interactivePrompt.data.items_per_port as Record<
            string,
            Array<{ index: number; port: string; ref: string; name: string; type: string }>
          >) ?? {}
        }
        onConfirm={(assignments) => {
          sendWebSocketMessage({
            type: "interactive_complete",
            block_id: interactivePrompt.blockId,
            data: { assignments },
          });
          setInteractivePrompt(null);
        }}
        onCancel={() => {
          sendWebSocketMessage({
            type: "cancel_block",
            block_id: interactivePrompt.blockId,
            workflow_id: workflowId,
          });
          setInteractivePrompt(null);
        }}
      />
    );
  }

  if (interactivePrompt?.blockType === "PairEditor") {
    return (
      <PairEditorModal
        blockId={interactivePrompt.blockId}
        ports={(interactivePrompt.data.ports as string[]) ?? []}
        itemsPerPort={
          (interactivePrompt.data.items_per_port as Record<
            string,
            Array<{ index: number; name: string; type: string }>
          >) ?? {}
        }
        collectionLength={(interactivePrompt.data.collection_length as number) ?? 0}
        onConfirm={(reorder) => {
          sendWebSocketMessage({
            type: "interactive_complete",
            block_id: interactivePrompt.blockId,
            data: { reorder },
          });
          setInteractivePrompt(null);
        }}
        onCancel={() => {
          sendWebSocketMessage({
            type: "cancel_block",
            block_id: interactivePrompt.blockId,
            workflow_id: workflowId,
          });
          setInteractivePrompt(null);
        }}
      />
    );
  }

  return null;
}
