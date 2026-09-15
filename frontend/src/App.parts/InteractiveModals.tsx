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

import { useRef } from "react";

import { submitPanelDecision } from "../panels/decisions";

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { INTERACTIVE_MEMORY_KEY, readInteractiveMemory } from "../lib/interactiveMemory";
import { useAppStore } from "../store";
import { executionViewKey } from "../store/executionSlice.parts/eventReducer";
import {
  interactivePromptKey,
  visibleInteractivePrompt,
} from "../store/executionSlice.parts/interactivePrompts";

import { InteractivePanel } from "../panels/InteractivePanel";
import { DynamicPanel } from "./InteractiveModals.parts/DynamicPanel";

export function InteractiveModals() {
  // #2395: prompts are held per (workflow, block). The window shows one at a
  // time — the one already shown while it is pending, else the oldest prompt of
  // the workflow on screen, else the oldest of any workflow — and answering it
  // surfaces the next (see `visibleInteractivePrompt`).
  const shownKey = useRef<string | null>(null);
  const interactivePrompt = useAppStore((s) =>
    visibleInteractivePrompt(s.interactivePrompts, executionViewKey(s), shownKey.current),
  );
  const removeInteractivePrompt = useAppStore((s) => s.removeInteractivePrompt);
  const promptKey = interactivePrompt
    ? interactivePromptKey(interactivePrompt.workflowId, interactivePrompt.blockId)
    : null;
  shownKey.current = promptKey;

  if (!interactivePrompt || promptKey === null) return null;

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
        // #2433: and the run, so a later run of the same workflow cannot take it.
        ...(interactivePrompt.runId ? { run_id: interactivePrompt.runId } : {}),
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
      const pending = useAppStore.getState().interactivePrompts;
      if (pending[promptKey] !== interactivePrompt) return;
    } else send();

    // ADR-051 interaction memory (Addendum 1): if this node has "remember and
    // skip" enabled, persist the decision + the run's input fingerprint into the
    // node config so future runs replay it without opening the dialog. Generic:
    // stores the verbatim response, no block-specific knowledge — so a package
    // block inherits it. Only persists when the user has opted in (enabled).
    //
    // #2362: read and write that config only while the prompt's workflow is
    // still the one on the canvas. `workflowNodes` and `updateNodeConfig` both
    // address the ACTIVE workflow, and this dialog is designed to survive a tab
    // switch — the same reason `promptWorkflowId` exists above. Without the
    // guard, switching tabs before Confirm either dropped the user's "remember
    // and skip" (the new workflow has no node with that id) or wrote one
    // workflow's decision and input fingerprint into a same-named node of
    // another, which the autosave then committed to disk.
    const state = useAppStore.getState();
    if (state.workflowId === promptWorkflowId) {
      const node = state.workflowNodes.find((n) => n.id === interactivePrompt.blockId);
      const memory = readInteractiveMemory(node?.config as Record<string, unknown> | undefined);
      if (memory?.enabled) {
        state.updateNodeConfig(interactivePrompt.blockId, {
          [INTERACTIVE_MEMORY_KEY]: {
            enabled: true,
            decision: responseData,
            signature: interactivePrompt.inputSignature,
          },
        });
      }
    }

    removeInteractivePrompt(promptWorkflowId, interactivePrompt.blockId);
  };

  const onCancel = () => {
    sendWebSocketMessage({
      type: "cancel_block",
      block_id: interactivePrompt.blockId,
      workflow_id: promptWorkflowId,
      ...(interactivePrompt.runId ? { run_id: interactivePrompt.runId } : {}),
    });
    removeInteractivePrompt(promptWorkflowId, interactivePrompt.blockId);
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
          // #2395: a different pending prompt is a different window — remount.
          key={promptKey}
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
        key={promptKey}
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
