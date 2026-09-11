import { dispatchWorkflowEvent } from "../hooks/useWebSocket.parts/dispatchEvent";
import { bootstrapFrame } from "../panels/testUtils";
/**
 * #2195 — the host must always offer a way out of an interactive block.
 *
 * These cover the manifest-resolution fork in `<InteractiveModals>`. Since
 * ADR-054 Phase B (#2294) there is no compiled `PANEL_REGISTRY`: a core panel
 * (empty `module_url`) and any package block that forgot `module_url` both route
 * through the sandboxed `<InteractivePanel>` host, while a package panel with a
 * `module_url` goes to `<DynamicPanel>`. The #2195 bug — a manifest carrying a
 * `panel_id` but no `module_url` resolving to a silent `null` — stays fixed:
 * that block registers, runs, and pauses, and must always get a visible window
 * with Cancel rather than a PAUSED run with only a `console.warn`.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import type { InteractivePrompt, PanelManifestDescriptor } from "../store/types";
import { resetAppStore } from "../testUtils";
import { InteractiveModals } from "./InteractiveModals";

vi.mock("../hooks/useWebSocket", () => ({
  sendWebSocketMessage: vi.fn(),
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { mockBackend, reply, type MockBackend } from "../__tests__/contract/mockBackend";
let backend: MockBackend;

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
  backend = mockBackend({
    "POST /api/panels/contexts": reply(404, {
      detail: { code: "not_found", message: "Panel myproj.foo not found" },
    }),
  });
  resetAppStore();
  // `resetAppStore` does not own the execution slice's prompt; clear it here so
  // a prompt seeded by one test cannot leak into the next.
  useAppStore.setState({ interactivePrompt: null });
  vi.mocked(sendWebSocketMessage).mockClear();
});

afterEach(() => {
  cleanup();
  backend?.restore();
});

describe("<InteractiveModals> panel resolution", () => {
  it("renders a visible error surface with a working Cancel for a manifest with no module_url", async () => {
    // The exact shape the issue describes: a block author wrote
    // `PanelManifest(panel_id="myproj.foo")` and forgot `module_url`.
    seedPrompt({ panel_id: "myproj.foo", api_version: "1" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    render(<InteractiveModals />);

    // A window exists at all — this is what used to be `null`.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const error = await screen.findByRole("alert");
    expect(error).toBeInTheDocument();
    // And it names the block, so the reader knows what is being waited on.
    expect(screen.getByRole("dialog")).toHaveTextContent("myproj.foo");

    fireEvent.click(screen.getAllByText("Cancel")[0]);
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
    await screen.findByRole("alert");

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(useAppStore.getState().interactivePrompt).toBeNull());
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "block-1",
      workflow_id: "wf-1",
    });
    warn.mockRestore();
  });

  it("routes a core panel (empty module_url) through the sandboxed panel host", () => {
    // ADR-054 Phase B (#2294): a core interactive window is a core-tier HTML
    // panel with an empty module_url, so it opens through <InteractivePanel> /
    // <PanelFrame> like every other core panel — not a compiled modal and not
    // the package dynamic-panel host.
    seedPrompt(
      { panel_id: "core.interactive.data_router" },
      {
        blockType: "data_router",
        panelPayload: { input_ports: ["in"], output_ports: ["out"], items_per_port: { in: [] } },
      },
    );

    render(<InteractiveModals />);

    // The sandboxed panel host mounts; the package dynamic-panel host does not.
    expect(screen.getByTestId("panel-host")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("data_router");
    expect(screen.queryByTestId("dynamic-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dynamic-panel-titlebar")).not.toBeInTheDocument();
  });

  it("routes a package manifest with a module_url to the dynamic panel host", () => {
    seedPrompt({
      panel_id: "myproj.foo",
      module_url: "/api/blocks/panels/myproj.foo/index.js",
      api_version: "1",
    });

    render(<InteractiveModals />);

    expect(screen.getByTestId("dynamic-panel")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("myproj.foo");
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

it.each(["accepted", "rejected"])(
  "waits for the server before closing or remembering a panel decision (%s)",
  async (outcome) => {
    backend.restore();
    backend = mockBackend({
      "POST /api/panels/contexts": {
        context_id: "pc-interactive",
        bootstrap_proof: "a".repeat(64),
        panel: { id: "lab.decision", api_version: "1.0", name: "Decision" },
        kind: "interactive",
        operations: ["writeBack"],
        services: ["save"],
        input: { question: "Choose" },
        token: "token",
        expires_at: 999999,
        entry_url: "/api/panels/t/token/assets/lab.decision/index.html",
        sdk_url: "/api/panels/t/token/sdk/1/scistudio-panel.js",
        lib_base_url: "/api/panels/t/token/lib/",
      },
      "DELETE /api/panels/contexts/{context_id}": reply(204),
    });
    const port = {
      onmessage: null,
      postMessage: vi.fn(),
      start: vi.fn(),
      close: vi.fn(),
    } as unknown as MessagePort;
    vi.stubGlobal(
      "MessageChannel",
      class {
        port1 = port;
        port2 = {};
      },
    );
    seedPrompt({ panel_id: "lab.decision", api_version: "1.0" });
    const originalUpdate = useAppStore.getState().updateNodeConfig;
    const remember = vi.fn();
    useAppStore.setState({
      workflowNodes: [
        {
          id: "block-1",
          block_type: "lab.decision",
          config: { interactive_memory: { enabled: true } },
        },
      ],
      updateNodeConfig: remember,
    });
    render(<InteractiveModals />);
    const iframe = (await screen.findByTitle("Decision")) as HTMLIFrameElement;
    bootstrapFrame(iframe);
    fireEvent.load(iframe);
    const message = async (type: string, payload: unknown) => {
      await act(async () => {
        await port.onmessage?.({ data: { v: 1, id: type, type, payload } } as MessageEvent);
      });
    };
    await message("ready", null);
    act(() => {
      void port.onmessage?.({
        data: { v: 1, id: "decision", type: "writeBack", payload: { selected: [2] } },
      } as MessageEvent);
    });
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      workflow_id: "wf-1",
      block_id: "block-1",
      context_id: "pc-interactive",
      data: { selected: [2] },
    });
    expect(useAppStore.getState().interactivePrompt).not.toBeNull();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(remember).not.toHaveBeenCalled();
    expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}")).toHaveLength(0);
    await act(async () => {
      const accepted = {
        type: outcome === "accepted" ? "panel_accepted" : "panel_error",
        error: { code: "stale_context", message: "Decision rejected: remount the panel" },
        context_id: "pc-interactive",
        workflow_id: "wf-1",
        block_id: "block-1",
        data: {},
        timestamp: "",
      };
      dispatchWorkflowEvent(accepted, {
        appendLog: vi.fn(),
        setWorkflow: vi.fn(),
        setInteractivePrompt: vi.fn(),
      });
    });
    if (outcome === "accepted") {
      expect(useAppStore.getState().interactivePrompt).toBeNull();
      expect(remember).toHaveBeenCalledWith("block-1", {
        interactive_memory: { enabled: true, decision: { selected: [2] }, signature: {} },
      });
    } else {
      expect(useAppStore.getState().interactivePrompt).not.toBeNull();
      expect(remember).not.toHaveBeenCalled();
      expect(await screen.findByRole("alert")).toHaveTextContent("Decision rejected");
      expect(screen.getByText("Remount panel")).toBeInTheDocument();
    }
    await waitFor(() =>
      expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}")).toHaveLength(1),
    );
    useAppStore.setState({ updateNodeConfig: originalUpdate });
    vi.unstubAllGlobals();
  },
);
