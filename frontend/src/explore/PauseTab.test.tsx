/**
 * ADR-054 spec 4 (T-010, T-011) — the pause tab that replaced the modal.
 *
 * **What must not change is the wire.** FR-025 says the backend's interactive
 * path is unchanged, so the assertions here are the ones the deleted
 * `interactiveModalsConfirm.test.tsx` made, moved to the surface that now sends
 * them: Confirm posts `interactive_complete` carrying the emission verbatim
 * under `code`, scoped to the workflow the *prompt* belongs to, and Cancel
 * posts `cancel_block` with the same scoping. `settle_interactive_response` in
 * `src/scistudio/blocks/base/interactive.py` reads exactly that shape, and
 * `tests/blocks/test_interactive_emission.py` pins the same snippets on the
 * Python side; if the two disagree a person presses Confirm and the block
 * errors.
 *
 * **Both built-ins are driven, deliberately.** `core.interactive.data_router`
 * and `core.interactive.pair_editor` used to reach a reader through a modal
 * whose host they shared; every existing interactive block is presented through
 * this tab now, so presentation is where the risk moved. Each is driven through
 * a real frame with its own emission, from the real event, to the real message.
 *
 * The prompt is delivered through `dispatchWorkflowEvent`, not by seeding the
 * store: the routing change is half the task, and a test that seeded the prompt
 * would pass with the dispatcher still opening a modal.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RealFrameSeam } from "../panels/__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "../panels/__tests__/support";
import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState } from "../store/types";
import { resetAppStore } from "../testUtils";
import type { ExploreSessionResponse, WorkflowEventMessage } from "../types/api";

import { ExploreNotebookPane, ExploreTab } from "./ExploreTab";
import { setPausePanelFrameFactory } from "./PanelSlots";

vi.mock("../hooks/useWebSocket", () => ({ sendWebSocketMessage: vi.fn() }));

const openExploreSession = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    openExploreSession: (...args: unknown[]) => openExploreSession(...args),
    windowExploreVariable: () => Promise.resolve({ session_id: "", name: "", envelope: {} }),
  },
}));

const getRuns = vi.fn();
vi.mock("../lib/api/lineage", () => ({
  lineageApi: { lineage: { getRuns: (...args: unknown[]) => getRuns(...args) } },
}));

vi.mock("../lib/api/data", () => ({
  dataApi: {
    listPanels: () => Promise.resolve({ panels: [], diagnostics: [] }),
    listPanelChoices: () => Promise.resolve({ choices: [] }),
  },
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { dispatchWorkflowEvent } from "../hooks/useWebSocket.parts/dispatchEvent";
import { readInteractiveMemory } from "../lib/interactiveMemory";

/** Verbatim from `src/scistudio/panels/builtin/core.interactive.data_router`. */
const ROUTING_DECISION =
  'assignments = {"port_1": ["input_1:0"], "port_2": []}\n' +
  "scistudio.output(assignments=assignments)";

/** Verbatim from `src/scistudio/panels/builtin/core.interactive.pair_editor`. */
const REORDER_DECISION = 'reorder = {"input_1": [1, 0]}\n' + "scistudio.output(reorder=reorder)";

function descriptor(panelId: string) {
  return {
    panel_id: panelId,
    display_name: panelId,
    api_version: "1",
    accepted_api_version: "1",
    capability: "producing",
    document_url: `/api/panels/assets/${panelId}/index.html`,
    asset_base_url: `/api/panels/assets/${panelId}/`,
    read_limits: { max_rows: 500, max_bytes: 1_000_000 },
  };
}

/** The event the engine's `_dispatch` emits when a block pauses. */
function promptEvent(overrides: Record<string, unknown> = {}): WorkflowEventMessage {
  return {
    type: "interactive_prompt",
    block_id: "node-1",
    workflow_id: "wf-prompt",
    data: {
      workflow_id: "wf-prompt",
      block_type: "data_router",
      panel_manifest: { panel_id: "core.interactive.data_router" },
      panel_descriptor: descriptor("core.interactive.data_router"),
      panel_payload: { input_ports: ["input_1"], output_ports: ["port_1", "port_2"] },
      input_signature: { input_1: ["alpha.tif"] },
      ...overrides,
    },
    timestamp: "2026-09-05T12:00:00Z",
  };
}

const deps = {
  appendLog: vi.fn(),
  setInteractivePrompt: (prompt: unknown) =>
    useAppStore.getState().setInteractivePrompt(prompt as never),
  setWorkflow: vi.fn(),
};

function pauseTab(): ExploreTabState {
  const tab = useAppStore.getState().tabs.find((candidate) => candidate.kind === "explore");
  if (!tab || tab.kind !== "explore") throw new Error("no Explore tab was opened for the pause");
  return tab;
}

/** Deliver the prompt, render the tab it opened, and drive its frame ready. */
async function openPause(event: WorkflowEventMessage = promptEvent()) {
  const seam = createRealFrameSeam();
  setPausePanelFrameFactory(seam.factory);
  act(() => {
    dispatchWorkflowEvent(event, deps);
  });
  const tab = pauseTab();
  render(<ExploreTab tab={tab} />);
  await act(async () => {
    seam.reportLoaded();
    await flush();
  });
  const init = receivedOfType(seam, "init")[0];
  const token = (init as unknown as { token: string }).token;
  await act(async () => {
    seam.fromPanel(token, "ready", { api_version: "1" });
    await flush();
  });
  await waitFor(() =>
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready"),
  );
  return { seam, token, tab };
}

async function emit(seam: RealFrameSeam, token: string, code: string) {
  await act(async () => {
    seam.fromPanel(token, "emit", { code });
    await flush();
  });
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({
    sessions: {},
    sessionPathById: {},
    pendingExploreEvents: {},
    tabs: [],
    activeTabId: null,
    interactivePrompt: null,
  });
  vi.mocked(sendWebSocketMessage).mockClear();
  openExploreSession.mockReset();
  getRuns.mockReset();
  getRuns.mockResolvedValue({ runs: [{ run_id: "run-7", workflow_id: "wf-prompt" }] });
});

afterEach(() => {
  setPausePanelFrameFactory(undefined);
  cleanup();
});

describe("the prompt opens an Explore tab, not a modal (FR-024)", () => {
  it("opens a pause tab over the paused block with no notebook pane", async () => {
    const { tab } = await openPause();

    expect(tab.mode).toBe("pause");
    expect(tab.pauseNodeId).toBe("node-1");
    expect(tab.sessionId).toBeNull();
    // FR-024 — the notebook pane is absent, which is the right column
    // rendering nothing at all.
    expect(tab.notebookVisible).toBe(false);
    const pane = render(<ExploreNotebookPane tab={tab} />);
    expect(pane.container.innerHTML).toBe("");
    pane.unmount();

    // The block's panel is mounted over the run's inputs, and confirm and
    // cancel are on the toolbar.
    expect(screen.getByTestId("explore-pause-panel")).toBeTruthy();
    expect(screen.getByTestId("panel-host")).toHaveAttribute(
      "data-panel-id",
      "core.interactive.data_router",
    );
    expect(screen.getByTestId("explore-pause-confirm")).toBeTruthy();
    expect(screen.getByTestId("explore-pause-cancel")).toBeTruthy();
    // Nothing was sent to the engine by opening the tab.
    expect(sendWebSocketMessage).not.toHaveBeenCalled();
  });

  it("still puts a window on screen when the prompt carried no descriptor", async () => {
    // #2195's property, carried across the migration: a person must never be
    // left on a paused block with no way out.
    act(() => {
      dispatchWorkflowEvent(promptEvent({ panel_descriptor: null }), deps);
    });
    render(<ExploreTab tab={pauseTab()} />);
    expect(await screen.findByTestId("panel-error-surface")).toBeTruthy();
    expect(screen.getByTestId("explore-pause-cancel")).toBeTruthy();
  });
});

describe("confirm and cancel send what the modal sent (FR-025)", () => {
  it("commits data_router's emission verbatim, scoped to the prompt's workflow", async () => {
    const { seam, token } = await openPause();

    // A producing panel's only outbound path is `emit`, so with nothing emitted
    // there is no decision to commit.
    expect(screen.getByTestId("explore-pause-confirm")).toBeDisabled();

    await emit(seam, token, ROUTING_DECISION);
    await waitFor(() => expect(screen.getByTestId("explore-pause-confirm")).toBeEnabled());
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));

    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      block_id: "node-1",
      workflow_id: "wf-prompt",
      data: { code: ROUTING_DECISION },
    });
    // The pause is over: the prompt is cleared and the tab says so. The tab
    // itself stays for the person to close — see `settle` in `PanelSlots.tsx`.
    expect(useAppStore.getState().interactivePrompt).toBeNull();
    expect(screen.getByTestId("explore-pause-resolved")).toBeTruthy();
  });

  it("commits pair_editor's emission through the very same path", async () => {
    const { seam, token } = await openPause(
      promptEvent({
        block_type: "pair_editor",
        panel_manifest: { panel_id: "core.interactive.pair_editor" },
        panel_descriptor: descriptor("core.interactive.pair_editor"),
        panel_payload: { pairs: [] },
      }),
    );
    expect(screen.getByTestId("panel-host")).toHaveAttribute(
      "data-panel-id",
      "core.interactive.pair_editor",
    );

    await emit(seam, token, REORDER_DECISION);
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));

    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      block_id: "node-1",
      workflow_id: "wf-prompt",
      data: { code: REORDER_DECISION },
    });
  });

  it("commits the newest emission, because each one is the whole decision", async () => {
    const { seam, token } = await openPause();
    await emit(seam, token, ROUTING_DECISION);
    await emit(seam, token, REORDER_DECISION);
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      block_id: "node-1",
      workflow_id: "wf-prompt",
      data: { code: REORDER_DECISION },
    });
  });

  it("cancels the block with the run-scoped cancellation", async () => {
    await openPause();
    fireEvent.click(screen.getByTestId("explore-pause-cancel"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "cancel_block",
      block_id: "node-1",
      workflow_id: "wf-prompt",
    });
    expect(useAppStore.getState().interactivePrompt).toBeNull();
  });

  it("records the emission as the remembered decision when the node opted in", async () => {
    useAppStore.setState({
      workflowNodes: [
        {
          id: "node-1",
          type: "block",
          position: { x: 0, y: 0 },
          data: {},
          config: { params: { interactive_memory: { enabled: true, decision: null } } },
        },
      ] as never,
    });
    const { seam, token } = await openPause();
    await emit(seam, token, ROUTING_DECISION);
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));

    const node = useAppStore.getState().workflowNodes.find((each) => each.id === "node-1");
    expect(readInteractiveMemory(node?.config as Record<string, unknown>)).toEqual({
      enabled: true,
      decision: { code: ROUTING_DECISION },
      signature: { input_1: ["alpha.tif"] },
    });
  });
});

describe("escalating to a notebook (FR-026)", () => {
  it("opens a session over the paused inputs while the block goes on waiting", async () => {
    const session: ExploreSessionResponse = {
      session_id: "sess-paused",
      notebook_path: "explore/node-1.ipynb",
      has_kernel: false,
      needs_restart: false,
      current_cell: null,
      notebook_commit: null,
      bound_run: {
        run_id: "run-7",
        block_id: "node-1",
        opened_over: "paused_run",
        ports: [{ name: "input_1", type_name: "Image", backend: "file", path: "a.tif" }],
      },
      cells: [],
    };
    openExploreSession.mockResolvedValue(session);

    await openPause();
    fireEvent.click(screen.getByTestId("explore-toolbar-notebook-toggle"));

    await waitFor(() =>
      expect(openExploreSession).toHaveBeenCalledWith({
        source: "paused_run",
        block_id: "node-1",
        run_id: "run-7",
      }),
    );

    // The pause has NOT resolved: nothing was sent to the engine and the prompt
    // is still on the store, so the block is still waiting for its decision.
    expect(sendWebSocketMessage).not.toHaveBeenCalled();
    expect(useAppStore.getState().interactivePrompt).not.toBeNull();

    // And the tab it landed in shows the notebook, still in pause mode.
    await waitFor(() => {
      const tab = pauseTab();
      expect(tab.notebookPath).toBe("explore/node-1.ipynb");
      expect(tab.mode).toBe("pause");
      expect(tab.notebookVisible).toBe(true);
      expect(tab.pauseNodeId).toBe("node-1");
    });
  });
});

describe("a packaged block asking (FR-027)", () => {
  it("opens the block's notebook in the same tab and confirms a notebook commit", async () => {
    const session: ExploreSessionResponse = {
      session_id: "sess-packaged",
      notebook_path: "explore/packaged.ipynb",
      has_kernel: false,
      needs_restart: false,
      current_cell: null,
      // The commit the person chose, as the runtime reports it.
      notebook_commit: "abc1234",
      bound_run: {
        run_id: "run-7",
        block_id: "node-1",
        opened_over: "paused_run",
        ports: [],
      },
      cells: [],
    };
    openExploreSession.mockResolvedValue(session);

    act(() => {
      dispatchWorkflowEvent(
        promptEvent({
          block_type: "MyNotebookBlock",
          // `EXPLORE_SESSION_PANEL_ID`: the tab itself is the panel, so there
          // is no frame to mount and the notebook is what the person decides in.
          panel_manifest: { panel_id: "core.explore.session" },
          panel_descriptor: null,
          panel_payload: {
            block_name: "MyNotebookBlock",
            notebook: "blocks/packaged.ipynb",
            notebook_commit: "abc1234",
            inputs: {},
          },
        }),
        deps,
      );
    });
    const { rerender } = render(<ExploreTab tab={pauseTab()} />);

    await waitFor(() =>
      expect(openExploreSession).toHaveBeenCalledWith({
        source: "paused_run",
        block_id: "node-1",
        run_id: "run-7",
      }),
    );
    await waitFor(() => expect(pauseTab().notebookPath).toBe("explore/packaged.ipynb"));

    const opened = pauseTab();
    expect(opened.notebookVisible).toBe(true);
    rerender(<ExploreTab tab={opened} />);
    const pane = render(<ExploreNotebookPane tab={opened} />);
    expect(pane.container.innerHTML).not.toBe("");
    pane.unmount();

    // The decision this block reads is a notebook commit (FR-047), not an
    // emission, and it is the commit the session reports.
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "interactive_complete",
      block_id: "node-1",
      workflow_id: "wf-prompt",
      data: { notebook_commit: "abc1234" },
    });
  });
});
