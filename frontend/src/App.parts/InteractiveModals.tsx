// Extracted from App.tsx as part of the #1422 god-file split.
//
// InteractiveModals — the interactive-block window that surfaces when a paused
// interactive block publishes its prompt on the workflow WebSocket.
//
// ADR-051: the panel is resolved from the block's panel manifest
// (`panel_manifest.panel_id`) via a built-in panel registry, NOT a hardcoded
// `blockType` branch (SC-006). Core panels resolve from PANEL_REGISTRY below; a
// package-provided panel loads via the ADR-048 same-origin dynamic-import path
// (`panel_manifest.module_url`) through <DynamicPanel> (FR-007).

import type { ReactElement } from "react";

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { INTERACTIVE_MEMORY_KEY, readInteractiveMemory } from "../lib/interactiveMemory";
import { useAppStore } from "../store";
import type { InteractivePrompt } from "../store/types";

import { DataRouterModal } from "../components/DataRouterModal";
import { PairEditorModal } from "../components/PairEditorModal";
import { DynamicPanel } from "./InteractiveModals.parts/DynamicPanel";

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

  if (!interactivePrompt) return null;

  // ADR-051: scope the response/cancel to the workflow the PROMPT belongs to —
  // not the store's currently-active workflow, which may have changed if the
  // user switched tabs while the prompt was open (codex P1).
  const promptWorkflowId = interactivePrompt.workflowId;

  const onConfirm = (responseData: Record<string, unknown>) => {
    sendWebSocketMessage({
      type: "interactive_complete",
      block_id: interactivePrompt.blockId,
      // ADR-051 audit P2-1: carry the prompt's workflow_id so the backend can
      // run-scope the response and not resolve a colliding block_id in another run.
      workflow_id: promptWorkflowId,
      data: responseData,
    });

    // ADR-051 interaction memory (Addendum 1): if this node has "remember and
    // skip" enabled, persist the decision + the run's input fingerprint into the
    // node config so future runs replay it without opening the dialog. Generic:
    // stores the verbatim response, no block-specific knowledge — so a package
    // block inherits it. Only persists when the user has opted in (enabled).
    const node = useAppStore
      .getState()
      .workflowNodes.find((n) => n.id === interactivePrompt.blockId);
    const memory = readInteractiveMemory(node?.config as Record<string, unknown> | undefined);
    if (memory?.enabled) {
      useAppStore.getState().updateNodeConfig(interactivePrompt.blockId, {
        [INTERACTIVE_MEMORY_KEY]: {
          enabled: true,
          decision: responseData,
          signature: interactivePrompt.inputSignature,
        },
      });
    }

    setInteractivePrompt(null);
  };

  const onCancel = () => {
    sendWebSocketMessage({
      type: "cancel_block",
      block_id: interactivePrompt.blockId,
      workflow_id: promptWorkflowId,
    });
    setInteractivePrompt(null);
  };

  const manifest = interactivePrompt.panelManifest;
  const panelId = manifest?.panel_id;
  const renderer = panelId ? PANEL_REGISTRY[panelId] : undefined;
  if (renderer) {
    // Core panel: resolved from the built-in registry (fast path, unchanged).
    return renderer({ prompt: interactivePrompt, onConfirm, onCancel });
  }

  // Package panel: a non-empty, backend-relative `module_url` loads the block's
  // window via the ADR-048 same-origin dynamic-import path. `onConfirm`/`onCancel`
  // are passed exactly as the registry entries receive them, so the run-scoped
  // `interactive_complete` / `cancel_block` frames are sent unchanged.
  const moduleUrl = manifest?.module_url;
  if (manifest && typeof moduleUrl === "string" && moduleUrl !== "") {
    return (
      <DynamicPanel
        manifest={manifest}
        blockId={interactivePrompt.blockId}
        panelPayload={interactivePrompt.panelPayload}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
  }

  // Neither a registered core panel nor a package `module_url`: nothing to
  // render. Warn so a misconfigured manifest is visible in the console.
  if (panelId) {
    console.warn(`[InteractiveModals] no registered panel for manifest panel_id "${panelId}"`);
  }
  return null;
}
