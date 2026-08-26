/**
 * #2195 — the host must always offer a way out of an interactive block.
 *
 * These cover the manifest-resolution fork in `<InteractiveModals>`: a core
 * panel still resolves from `PANEL_REGISTRY`, a package panel still goes to
 * `<DynamicPanel>`, and — the bug — a manifest that carries a `panel_id` but no
 * `module_url` no longer resolves to a silent `null`. `PanelManifest.module_url`
 * defaults to `""` and the registry only requires a non-empty `panel_id`, so
 * that block registers, runs, and pauses; before this fix the run sat in PAUSED
 * with no window at all and only a `console.warn` to show for it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import type { InteractivePrompt, PanelManifestDescriptor } from "../store/types";
import { resetAppStore } from "../testUtils";
import { InteractiveModals } from "./InteractiveModals";

vi.mock("../hooks/useWebSocket", () => ({
  sendWebSocketMessage: vi.fn(),
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";

function seedPrompt(
  manifest: PanelManifestDescriptor | null,
  overrides: Partial<InteractivePrompt> = {},
) {
  const prompt: InteractivePrompt = {
    blockId: "block-1",
    blockType: "myproj.foo",
    workflowId: "wf-1",
    panelManifest: manifest,
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
  it("renders a visible error surface with a working Cancel for a manifest with no module_url", async () => {
    // The exact shape the issue describes: a block author wrote
    // `PanelManifest(panel_id="myproj.foo")` and forgot `module_url`.
    seedPrompt({ panel_id: "myproj.foo", api_version: "1" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    render(<InteractiveModals />);

    // A window exists at all — this is what used to be `null`.
    expect(screen.getByTestId("dynamic-panel")).toBeInTheDocument();
    const error = await screen.findByTestId("dynamic-panel-error");
    expect(error).toBeInTheDocument();
    // And it names the block, so the reader knows what is being waited on.
    expect(screen.getByTestId("dynamic-panel-titlebar")).toHaveTextContent("myproj.foo");

    fireEvent.click(screen.getByTestId("dynamic-panel-cancel"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "block-1",
      workflow_id: "wf-1",
    });
    expect(useAppStore.getState().interactivePrompt).toBeNull();
    warn.mockRestore();
  });

  it("cancels that misconfigured-manifest window on ESC too", async () => {
    seedPrompt({ panel_id: "myproj.foo", api_version: "1" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    render(<InteractiveModals />);
    await screen.findByTestId("dynamic-panel-error");

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(useAppStore.getState().interactivePrompt).toBeNull());
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "block-1",
      workflow_id: "wf-1",
    });
    warn.mockRestore();
  });

  it("still resolves a core panel from the registry, untouched by the host chrome", () => {
    seedPrompt(
      { panel_id: "core.interactive.data_router" },
      {
        blockType: "data_router",
        panelPayload: { input_ports: ["in"], output_ports: ["out"], items_per_port: { in: [] } },
      },
    );

    render(<InteractiveModals />);

    // The core modal renders itself; no dynamic-panel host chrome is involved.
    expect(screen.queryByTestId("dynamic-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dynamic-panel-titlebar")).not.toBeInTheDocument();
  });

  it("routes a package manifest with a module_url to the dynamic panel host", () => {
    seedPrompt({
      panel_id: "myproj.foo",
      module_url: "/api/interactive/panels/myproj.foo/index.js",
      api_version: "1",
    });

    render(<InteractiveModals />);

    expect(screen.getByTestId("dynamic-panel")).toBeInTheDocument();
    expect(screen.getByTestId("dynamic-panel-titlebar")).toHaveTextContent("myproj.foo");
  });

  it("renders nothing when the prompt carries no panel manifest", () => {
    seedPrompt(null);
    const { container } = render(<InteractiveModals />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there is no interactive prompt", () => {
    const { container } = render(<InteractiveModals />);
    expect(container).toBeEmptyDOMElement();
  });
});
