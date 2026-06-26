// Extracted from App.tsx as part of the #1422 god-file split.
//
// InteractiveModals — the interactive-block window that surfaces when a paused
// interactive block publishes its prompt on the workflow WebSocket.
//
// ADR-051: the panel is resolved from the block's panel manifest
// (`panel_manifest.panel_id`) via a built-in panel registry, NOT a hardcoded
// `blockType` branch (SC-006). Core panels resolve from PANEL_REGISTRY below; a
// package-provided panel would load via the ADR-048 same-origin dynamic-import
// path (`panel_manifest.module_url`), which is out of scope for this change.

import type { ReactElement } from "react";

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { useAppStore } from "../store";
import type { InteractivePrompt } from "../store/types";

import { DataRouterModal } from "../components/DataRouterModal";
import { PairEditorModal } from "../components/PairEditorModal";

interface PanelRenderProps {
  prompt: InteractivePrompt;
  /** Send the panel's JSON-safe decision back to the backend. */
  onConfirm: (responseData: Record<string, unknown>) => void;
  onCancel: () => void;
}

type PanelRenderer = (props: PanelRenderProps) => ReactElement;

/**
 * ADR-051 panel registry: maps a manifest `panel_id` to the core component that
 * renders the block's window. Each entry adapts the block's `panelPayload` to
 * its component's props and maps the component's result to the JSON-safe
 * `interactive_response` the block expects. Adding a core interactive block is a
 * new registry entry — never a new `blockType` branch.
 */
const PANEL_REGISTRY: Record<string, PanelRenderer> = {
  "core.interactive.data_router": ({ prompt, onConfirm, onCancel }) => (
    <DataRouterModal
      blockId={prompt.blockId}
      inputPorts={(prompt.panelPayload.input_ports as string[]) ?? []}
      outputPorts={(prompt.panelPayload.output_ports as string[]) ?? []}
      itemsPerPort={
        (prompt.panelPayload.items_per_port as Record<
          string,
          Array<{ index: number; port: string; ref: string; name: string; type: string }>
        >) ?? {}
      }
      onConfirm={(assignments) => onConfirm({ assignments })}
      onCancel={onCancel}
    />
  ),
  "core.interactive.pair_editor": ({ prompt, onConfirm, onCancel }) => (
    <PairEditorModal
      blockId={prompt.blockId}
      ports={(prompt.panelPayload.ports as string[]) ?? []}
      itemsPerPort={
        (prompt.panelPayload.items_per_port as Record<
          string,
          Array<{ index: number; name: string; type: string }>
        >) ?? {}
      }
      collectionLength={(prompt.panelPayload.collection_length as number) ?? 0}
      onConfirm={(reorder) => onConfirm({ reorder })}
      onCancel={onCancel}
    />
  ),
};

export function InteractiveModals() {
  const interactivePrompt = useAppStore((s) => s.interactivePrompt);
  const setInteractivePrompt = useAppStore((s) => s.setInteractivePrompt);
  const workflowId = useAppStore((s) => s.workflowId);

  if (!interactivePrompt) return null;

  const panelId = interactivePrompt.panelManifest?.panel_id;
  const renderer = panelId ? PANEL_REGISTRY[panelId] : undefined;
  if (!renderer) {
    if (panelId) {
      // A package panel (manifest.module_url) would be dynamically imported here
      // via the ADR-048 mechanism; core panels resolve from the registry above.
      console.warn(`[InteractiveModals] no registered panel for manifest panel_id "${panelId}"`);
    }
    return null;
  }

  const onConfirm = (responseData: Record<string, unknown>) => {
    sendWebSocketMessage({
      type: "interactive_complete",
      block_id: interactivePrompt.blockId,
      data: responseData,
    });
    setInteractivePrompt(null);
  };

  const onCancel = () => {
    sendWebSocketMessage({
      type: "cancel_block",
      block_id: interactivePrompt.blockId,
      workflow_id: workflowId,
    });
    setInteractivePrompt(null);
  };

  return renderer({ prompt: interactivePrompt, onConfirm, onCancel });
}
