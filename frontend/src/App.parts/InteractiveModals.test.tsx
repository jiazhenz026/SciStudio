/**
 * ADR-054 spec 1, T-007 / D-018 — the interactive-block window.
 *
 * Two properties are defended here, and they are not the same property.
 *
 * The first is #2195's P1, carried across the migration unchanged: **a person
 * must never be stuck on a paused block with no exit.** The overlay covers the
 * toolbar's Stop control, so a window that failed to draw used to leave the
 * whole application unreachable. Every failure mode still renders a window with
 * a title bar, a close control, a Cancel button and an ESC binding.
 *
 * The second is FR-037: the built-in `PANEL_REGISTRY` is gone, so a core panel
 * id no longer resolves to a compiled React component. `core.interactive.*` is
 * mounted from the descriptor the backend resolved for it, exactly as a package
 * panel is — one mechanism, not two.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import type { InteractivePrompt, PanelManifestDescriptor } from "../store/types";
import { resetAppStore } from "../testUtils";
import type { PanelDescriptorResponse } from "../types/api";
import { InteractiveModals } from "./InteractiveModals";

vi.mock("../hooks/useWebSocket", () => ({
  sendWebSocketMessage: vi.fn(),
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";

/** A descriptor shaped exactly as `PanelDescriptor.to_dict()` emits it. */
function descriptor(panelId: string): PanelDescriptorResponse {
  return {
    panel_id: panelId,
    display_name: panelId,
    api_version: "1",
    accepted_api_version: "1",
    capability: "producing",
    document_url: `/api/panels/assets/${panelId}/index.html`,
    asset_base_url: `/api/panels/assets/${panelId}/`,
    read_limits: { max_rows: 100, max_bytes: 1000 },
  };
}

function seedPrompt(
  manifest: PanelManifestDescriptor | null,
  overrides: Partial<InteractivePrompt> = {},
) {
  const prompt: InteractivePrompt = {
    blockId: "block-1",
    blockType: "myproj.foo",
    workflowId: "wf-1",
    panelManifest: manifest,
    panelDescriptor: null,
    panelPayload: {},
    inputSignature: {},
    data: {},
    ...overrides,
  };
  useAppStore.setState({ interactivePrompt: prompt });
  return prompt;
}

beforeEach(() => {
  resetAppStore();
  // `resetAppStore` does not own the execution slice's prompt; clear it here so
  // a prompt seeded by one test cannot leak into the next.
  useAppStore.setState({ interactivePrompt: null });
  vi.mocked(sendWebSocketMessage).mockClear();
});

afterEach(cleanup);

describe("<InteractiveModals> panel resolution", () => {
  it("renders a visible error surface with a working Cancel when no descriptor was sent", async () => {
    // The migrated shape of the #2195 bug: the prompt names a panel but carries
    // no descriptor for it, so there is no document to mount.
    seedPrompt({ panel_id: "myproj.foo", api_version: "1" });

    render(<InteractiveModals />);

    // A window exists at all — this is what used to be `null`.
    expect(screen.getByTestId("interactive-panel")).toBeInTheDocument();
    const error = await screen.findByTestId("panel-error-surface");
    expect(error).toHaveTextContent("myproj.foo");
    // And it names the block, so the reader knows what is being waited on.
    expect(screen.getByTestId("interactive-panel-titlebar")).toHaveTextContent("myproj.foo");

    fireEvent.click(screen.getByTestId("interactive-panel-cancel"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "block-1",
      workflow_id: "wf-1",
    });
    expect(useAppStore.getState().interactivePrompt).toBeNull();
  });

  it("cancels that window on ESC too", async () => {
    seedPrompt({ panel_id: "myproj.foo", api_version: "1" });

    render(<InteractiveModals />);
    await screen.findByTestId("panel-error-surface");

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(useAppStore.getState().interactivePrompt).toBeNull());
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "block-1",
      workflow_id: "wf-1",
    });
  });

  it("mounts a core interactive panel through the frame host, not a registry entry", () => {
    // FR-037: `core.interactive.data_router` is a panel directory now. It goes
    // through the same host a package panel does, and there is no compiled
    // component behind its id to short-circuit to.
    seedPrompt(
      { panel_id: "core.interactive.data_router" },
      {
        blockType: "data_router",
        panelDescriptor: descriptor("core.interactive.data_router"),
        panelPayload: { input_ports: ["in"], output_ports: ["out"], items_per_port: { in: [] } },
      },
    );

    render(<InteractiveModals />);

    expect(screen.getByTestId("interactive-panel")).toBeInTheDocument();
    expect(screen.getByTestId("panel-host")).toHaveAttribute(
      "data-panel-id",
      "core.interactive.data_router",
    );
    expect(screen.getByTestId("interactive-panel-titlebar")).toHaveTextContent("data_router");
  });

  it("mounts a package panel through the very same host", () => {
    seedPrompt(
      { panel_id: "myproj.foo", api_version: "1" },
      { panelDescriptor: descriptor("myproj.foo") },
    );

    render(<InteractiveModals />);

    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-id", "myproj.foo");
  });

  it("keeps Confirm disabled until the panel has emitted a decision (D-018)", () => {
    seedPrompt(
      { panel_id: "myproj.foo", api_version: "1" },
      { panelDescriptor: descriptor("myproj.foo") },
    );

    render(<InteractiveModals />);

    // A producing panel's only outbound path is `emit`, so Confirm belongs to
    // the host — and with nothing emitted there is nothing to commit.
    expect(screen.getByTestId("interactive-panel-confirm")).toBeDisabled();
  });

  it("still renders the window when the prompt carries no manifest at all", () => {
    seedPrompt(null);
    render(<InteractiveModals />);
    // Not `null`: the block IS paused and the only way out of it must stay on
    // screen, whatever the prompt failed to name.
    expect(screen.getByTestId("interactive-panel-cancel")).toBeInTheDocument();
  });

  it("renders nothing when there is no interactive prompt", () => {
    const { container } = render(<InteractiveModals />);
    expect(container).toBeEmptyDOMElement();
  });
});
