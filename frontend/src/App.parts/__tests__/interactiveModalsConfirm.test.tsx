/**
 * ADR-054 spec 1 FR-012 / D-018 — the hop from Confirm to the backend.
 *
 * `InteractiveModals.test.tsx` owns the #2195 no-exit property and the panel
 * resolution; this file owns the one link neither of those covers: what
 * actually goes onto the WebSocket when the host commits an emission, and that
 * it is run-scoped to the prompt's own workflow.
 *
 * The host is stubbed here on purpose. Driving a real emission through a real
 * sandboxed frame is
 * `InteractiveModals.parts/__tests__/interactivePanelHost.test.tsx`'s job; what
 * is under test here is `InteractiveModals`, which must forward whatever the
 * host commits **verbatim** — it is deliberately ignorant of what an emission
 * is, because interpreting it is the backend's
 * (`settle_interactive_response`, FR-012).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import type { InteractivePrompt } from "../../store/types";
import { resetAppStore } from "../../testUtils";

vi.mock("../../hooks/useWebSocket", () => ({ sendWebSocketMessage: vi.fn() }));

/**
 * A stand-in for the frame host: one button that commits an emission, exactly
 * as the real Confirm does once a panel has emitted.
 */
vi.mock("../InteractiveModals.parts/InteractivePanelHost", () => ({
  InteractivePanelHost: ({
    onConfirm,
  }: {
    onConfirm: (payload: Record<string, unknown>) => void;
  }) => (
    <button type="button" data-testid="stub-confirm" onClick={() => onConfirm({ code: EMISSION })}>
      confirm
    </button>
  ),
}));

import { sendWebSocketMessage } from "../../hooks/useWebSocket";
import { readInteractiveMemory } from "../../lib/interactiveMemory";
import { InteractiveModals } from "../InteractiveModals";

/** Verbatim from the shipped `core.interactive.data_router` document. */
const EMISSION =
  'assignments = {"port_1": ["input_1:0"], "port_2": []}\nscistudio.output(assignments=assignments)';

function seedPrompt(overrides: Partial<InteractivePrompt> = {}) {
  useAppStore.setState({
    interactivePrompt: {
      blockId: "node-1",
      blockType: "data_router",
      workflowId: "wf-prompt",
      panelManifest: { panel_id: "core.interactive.data_router" },
      panelDescriptor: null,
      panelPayload: {},
      inputSignature: { input_1: ["alpha.tif"] },
      data: {},
      ...overrides,
    },
  });
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ interactivePrompt: null });
  vi.mocked(sendWebSocketMessage).mockClear();
});

afterEach(cleanup);

describe("committing an emission over interactive_complete", () => {
  it("forwards the emission verbatim, scoped to the prompt's own workflow", () => {
    seedPrompt();
    render(<InteractiveModals />);

    screen.getByTestId("stub-confirm").click();

    // `data` is what `_on_interactive_complete` hands to
    // `settle_interactive_response`: one key, `code`, holding the snippet
    // unchanged. Nothing here parses it or repackages it.
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      block_id: "node-1",
      workflow_id: "wf-prompt",
      data: { code: EMISSION },
    });
    expect(useAppStore.getState().interactivePrompt).toBeNull();
  });

  it("records the emission as the remembered decision when the node opted in", () => {
    // ADR-051 interaction memory replays a saved decision instead of opening
    // the dialog, and the engine settles a replayed emission through the same
    // path — so storing the snippet verbatim is what makes the replay produce
    // the same routing rather than a stale or unreadable one.
    seedPrompt();
    useAppStore.setState({
      workflowNodes: [
        {
          id: "node-1",
          type: "block",
          position: { x: 0, y: 0 },
          data: {},
          // Where the Config panel's "Remember my choice" toggle actually
          // leaves it: `updateNodeConfig` deep-merges into `config.params`.
          config: { params: { interactive_memory: { enabled: true, decision: null } } },
        },
      ] as never,
    });

    render(<InteractiveModals />);
    screen.getByTestId("stub-confirm").click();

    const node = useAppStore.getState().workflowNodes.find((each) => each.id === "node-1");
    // Read it back the way the store's own reader does: `updateNodeConfig`
    // deep-merges into `config.params`, and `readInteractiveMemory` looks in
    // both places for exactly that reason.
    expect(readInteractiveMemory(node?.config as Record<string, unknown>)).toEqual({
      enabled: true,
      decision: { code: EMISSION },
      signature: { input_1: ["alpha.tif"] },
    });
  });
});
