// Extracted from App.tsx as part of the #1422 god-file split.
//
// InteractiveModals — the interactive-block window that surfaces when a paused
// interactive block publishes its prompt on the workflow WebSocket.
//
// ADR-054 FR-037, T-007: the built-in `PANEL_REGISTRY` that mapped
// `core.interactive.data_router` and `core.interactive.pair_editor` to compiled
// React components is gone. Those two are panel directories like any other now,
// discovered and resolved through the four tiers, and shadowable from the user
// library or the project on the same terms as any other panel. A core panel and
// a package panel therefore reach the reader through exactly one path — the
// sandboxed frame — instead of the two that used to sit side by side, which is
// the "one mechanism" property ADR-054 §9 is written to protect.
//
// What this component still owns is the run scoping: the response and the
// cancel are addressed to the workflow the *prompt* belongs to, never to the
// store's currently-active workflow, and the interaction memory is recorded
// from the same verbatim response.

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { INTERACTIVE_MEMORY_KEY, readInteractiveMemory } from "../lib/interactiveMemory";
import { useAppStore } from "../store";

import { InteractivePanelHost } from "./InteractiveModals.parts/InteractivePanelHost";

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

  // The window renders as soon as a prompt exists, even when the prompt named
  // no panel this host can mount: the overlay covers the toolbar's Stop
  // control, so returning `null` here would leave a person on a paused block
  // with no window and no exit (#2195). `InteractivePanelHost` draws the error
  // surface with Cancel beside it for exactly that case.
  return (
    <InteractivePanelHost
      descriptor={interactivePrompt.panelDescriptor}
      panelId={interactivePrompt.panelManifest?.panel_id ?? null}
      blockId={interactivePrompt.blockId}
      blockName={interactivePrompt.blockType}
      panelPayload={interactivePrompt.panelPayload}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
