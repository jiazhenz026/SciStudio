// Extracted from App.tsx as part of the #1422 god-file split.
//
// InteractiveModals — the interactive-block window that surfaces when a paused
// interactive block publishes its prompt on the workflow WebSocket.
//
// ADR-051 / ADR-054 Phase B: the panel is resolved from the block's panel
// manifest (`panel_manifest.panel_id`), NOT a hardcoded `blockType` branch
// (SC-006). Since Phase B (#2294) there is no compiled built-in panel registry:
// a core interactive window (`core.interactive.data_router`,
// `core.interactive.pair_editor`) is itself a core-tier HTML panel with an
// empty `module_url`, so it routes through the same sandboxed <InteractivePanel>
// host every other core panel uses. A package-provided panel loads via the
// ADR-048 same-origin dynamic-import path (`panel_manifest.module_url`) through
// <DynamicPanel> (FR-007).

import { submitPanelDecision } from "../panels/decisions";

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { INTERACTIVE_MEMORY_KEY, readInteractiveMemory } from "../lib/interactiveMemory";
import { useAppStore } from "../store";

import { InteractivePanel } from "../panels/InteractivePanel";
import { DynamicPanel } from "./InteractiveModals.parts/DynamicPanel";

export function InteractiveModals() {
  const interactivePrompt = useAppStore((s) => s.interactivePrompt);
  const setInteractivePrompt = useAppStore((s) => s.setInteractivePrompt);

  if (!interactivePrompt) return null;

  // ADR-051: scope the response/cancel to the workflow the PROMPT belongs to —
  // not the store's currently-active workflow, which may have changed if the
  // user switched tabs while the prompt was open (codex P1).
  const promptWorkflowId = interactivePrompt.workflowId;

  const onConfirm = async (
    responseData: Record<string, unknown>,
    contextId?: string,
    signal?: AbortSignal,
  ) => {
    const send = () =>
      sendWebSocketMessage({
        type: "interactive_complete",
        block_id: interactivePrompt.blockId,
        // ADR-051 audit P2-1: carry the prompt's workflow_id so the backend can
        // run-scope the response and not resolve a colliding block_id in another run.
        workflow_id: promptWorkflowId,
        data: responseData,
        ...(contextId ? { context_id: contextId } : {}),
      });

    if (contextId) {
      await submitPanelDecision(
        {
          context_id: contextId,
          workflow_id: promptWorkflowId,
          block_id: interactivePrompt.blockId,
        },
        send,
        signal,
      );
      if (useAppStore.getState().interactivePrompt !== interactivePrompt) return;
    } else send();

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

  // A manifest with an empty `module_url` — every core interactive panel
  // (`core.interactive.*`) and any package block that forgot `module_url` —
  // routes through the sandboxed <InteractivePanel> host, which opens the
  // block's interactive panel context and mounts the panel's HTML entry.
  //
  // #2195 — a block that forgets `module_url` still gets a visible window with
  // Cancel here rather than a silent PAUSED run: the host surfaces the panel's
  // load/registration failure with a Cancel + Remount surface, so the run is
  // never trapped. A non-empty, backend-relative `module_url` loads a
  // package-provided window via the ADR-048 same-origin dynamic-import path
  // through <DynamicPanel>. `onConfirm`/`onCancel` are passed unchanged in both
  // cases, so the run-scoped `interactive_complete` / `cancel_block` frames are
  // sent identically.
  if (manifest) {
    if (!manifest.module_url) {
      return (
        <InteractivePanel
          panelId={manifest.panel_id}
          workflowId={promptWorkflowId}
          blockId={interactivePrompt.blockId}
          blockName={interactivePrompt.blockType}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    }
    return (
      <DynamicPanel
        manifest={manifest}
        blockId={interactivePrompt.blockId}
        blockName={interactivePrompt.blockType}
        panelPayload={interactivePrompt.panelPayload}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
  }

  // No panel manifest at all: this prompt does not describe a window, so there
  // is nothing for the host to draw and no overlay to trap the user behind —
  // the Toolbar's Stop control stays reachable.
  return null;
}
