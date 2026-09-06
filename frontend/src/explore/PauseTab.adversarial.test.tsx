/**
 * ADR-054 spec 4 — adversarial tests against the pause tab (S4-D1, #2253).
 *
 * `PauseTab.test.tsx` proves the happy path of FR-024 to FR-027 and it proves
 * it well: the prompt opens a tab rather than a modal, and Confirm and Cancel
 * put `interactive_complete` and `cancel_block` on the wire in the shape the
 * deleted modal put them, scoped to the prompt's own workflow. Every one of its
 * cases answers exactly one prompt exactly once.
 *
 * §4.5 says the modal's retirement is a presentation-only risk: *"Its confirm
 * and cancel send the messages the modal sent, so the backend path is
 * untouched; the risk is confined to presentation."* That is true of the
 * message shapes. It is not true of the **lifecycle**, and the lifecycle is
 * what changed: a modal was one window that could not be left, could not be
 * duplicated, and whose every exit — the close control, ESC, the Cancel
 * button — drove the same run-scoped `cancel_block`. A tab can be closed, left,
 * and joined by a second one.
 *
 * The baseline these tests measure against is the deleted component itself,
 * read out of git history at `c3ba855b4^`:
 * `frontend/src/App.parts/InteractiveModals.tsx` and its
 * `InteractiveModals.parts/InteractivePanelHost.tsx`. Its own header states the
 * property being defended, from #2195: *"a person must never be left on a
 * paused block with no window and no way out."*
 *
 * Findings are recorded in `docs/planning/adr-054-assembly-followups.md` under
 * `### S4-D1 / S5-D1 (adversarial testing)`.
 *
 * **Every `it.fails(...)` in this file is a confirmed defect, not a disabled
 * test.** The assertion inside it is the behaviour the spec asks for, written
 * exactly as it would be written if the implementation had it; `it.fails` is
 * vitest's declaration that the code under test does **not** have it yet. The
 * body still runs and still exercises the real code, so the marker is not
 * silence: the day the defect is fixed, the marked test starts failing and
 * whoever fixed it must delete the marker. Nothing here was weakened to make it
 * pass. The markers exist so the assembly's CI can tell S4-D1's deliberate red
 * from a regression; delete them all with one `sed` to see the raw failures.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RealFrameSeam } from "../panels/__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "../panels/__tests__/support";
import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState } from "../store/types";
import { resetAppStore } from "../testUtils";
import type { WorkflowEventMessage } from "../types/api";

import { ExploreTab } from "./ExploreTab";
import { setPausePanelFrameFactory } from "./PanelSlots";

vi.mock("../hooks/useWebSocket", () => ({ sendWebSocketMessage: vi.fn() }));

vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    openExploreSession: () => Promise.reject(new Error("no session is opened by these tests")),
    windowExploreVariable: () => Promise.resolve({ session_id: "", name: "", envelope: {} }),
  },
}));

vi.mock("../lib/api/lineage", () => ({
  lineageApi: { lineage: { getRuns: () => Promise.resolve({ runs: [] }) } },
}));

vi.mock("../lib/api/data", () => ({
  dataApi: {
    listPanels: () => Promise.resolve({ panels: [], diagnostics: [] }),
    listPanelChoices: () => Promise.resolve({ choices: [] }),
  },
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { dispatchWorkflowEvent } from "../hooks/useWebSocket.parts/dispatchEvent";

/** Verbatim from `src/scistudio/panels/builtin/core.interactive.data_router`. */
const ROUTING_DECISION =
  'assignments = {"port_1": ["input_1:0"], "port_2": []}\n' +
  "scistudio.output(assignments=assignments)";

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
function promptEvent(blockId = "node-1", workflowId = "wf-prompt"): WorkflowEventMessage {
  return {
    type: "interactive_prompt",
    block_id: blockId,
    workflow_id: workflowId,
    data: {
      workflow_id: workflowId,
      block_type: "data_router",
      panel_manifest: { panel_id: "core.interactive.data_router" },
      panel_descriptor: descriptor("core.interactive.data_router"),
      panel_payload: { input_ports: ["input_1"], output_ports: ["port_1", "port_2"] },
      input_signature: { input_1: ["alpha.tif"] },
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

function tabForBlock(blockId: string): ExploreTabState {
  const tab = useAppStore
    .getState()
    .tabs.find((candidate) => candidate.kind === "explore" && candidate.pauseNodeId === blockId);
  if (!tab || tab.kind !== "explore") throw new Error(`no pause tab for ${blockId}`);
  return tab;
}

function sentOfType(type: string) {
  return vi
    .mocked(sendWebSocketMessage)
    .mock.calls.map(([message]) => message as Record<string, unknown>)
    .filter((message) => message.type === type);
}

/** Deliver a prompt and drive its frame to ready; returns the seam and token. */
async function openPause(event: WorkflowEventMessage) {
  const seam = createRealFrameSeam();
  setPausePanelFrameFactory(seam.factory);
  act(() => {
    dispatchWorkflowEvent(event, deps);
  });
  const tab = tabForBlock(event.block_id as string);
  const view = render(<ExploreTab tab={tab} />);
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
  return { seam, token, tab, view };
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
});

afterEach(() => {
  setPausePanelFrameFactory(undefined);
  cleanup();
});

/* -------------------------------------------------------------------------- */
/* Answering the same pause twice (FR-025)                                     */
/* -------------------------------------------------------------------------- */

describe("a pause can only be answered once", () => {
  /**
   * Proves: pressing Confirm twice puts exactly one `interactive_complete` on
   * the wire — a **negative result**, recorded so the manager knows this
   * ground is covered.
   *
   * Why the existing tests did not: every case in `PauseTab.test.tsx` presses
   * Confirm once. The control is not disabled after it is pressed — it is only
   * disabled while `decision === null` — so the guard is `onConfirm`'s early
   * return on a cleared prompt, and a guard nobody exercised is a guard nobody
   * knows is there. A second `interactive_complete` would be a second decision
   * for one paused block: `settle_interactive_response` would apply the first
   * and the block would already have resumed.
   */
  it("sends one interactive_complete for two presses of Confirm", async () => {
    const { seam, token } = await openPause(promptEvent());
    await emit(seam, token, ROUTING_DECISION);

    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    await act(async () => {
      await flush();
    });

    expect(sentOfType("interactive_complete")).toHaveLength(1);
  });

  /**
   * Proves: Cancel after a Confirm sends nothing — a **negative result**.
   *
   * Why the existing tests did not: confirm and cancel are each driven from a
   * fresh pause. The tab, unlike the modal, is still on screen with both
   * controls live after the answer is sent, so "cancel a block that already
   * resumed" is a sequence a person can now perform and the modal could not
   * offer. `cancel_block` reaching a block that already resumed is the failure
   * being ruled out.
   */
  it("sends no cancel_block for a Cancel pressed after Confirm", async () => {
    const { seam, token } = await openPause(promptEvent());
    await emit(seam, token, ROUTING_DECISION);

    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    await act(async () => {
      await flush();
    });
    fireEvent.click(screen.getByTestId("explore-pause-cancel"));
    await act(async () => {
      await flush();
    });

    expect(sentOfType("interactive_complete")).toHaveLength(1);
    expect(sentOfType("cancel_block")).toHaveLength(0);
  });
});

/* -------------------------------------------------------------------------- */
/* Leaving a pause unanswered (FR-024, and #2195's property)                   */
/* -------------------------------------------------------------------------- */

describe("a pause tab is the block's only window", () => {
  /**
   * Proves: closing an unanswered pause tab sends nothing, and leaves the
   * paused block with no window and no way back.
   *
   * The deleted modal made this impossible. Its close control, its ESC binding
   * and its Cancel button all drove one run-scoped `cancel_block`
   * (`InteractivePanelHost`, `handleClose`), and its header says why: *"this
   * overlay covers the toolbar's Stop control, so a panel that wires no exit of
   * its own would leave the whole application unreachable"* (#2195). The tab
   * does not cover the Stop control, so that half of #2195 is answered — but
   * the other half is not: after `closeTab` the prompt is still in the store,
   * the block is still paused on the backend, and nothing on screen can answer
   * it. `openPauseTab` is called from exactly one place, the
   * `interactive_prompt` branch of `dispatchWorkflowEvent`, so the tab cannot
   * be reopened; the run has to be stopped.
   *
   * Why the existing tests did not: no test in the suite closes a pause tab.
   * The tab's own lifecycle is the part of the migration that has no
   * counterpart in the component it replaced, which is exactly why nothing
   * carried a test across.
   *
   * Left failing. The assertion is the modal's contract — an exit answers the
   * block — and the repair may equally be "closing sends the cancellation" or
   * "closing a live pause is refused, as a dirty file tab is". Either satisfies
   * this test's intent; it is written against the first because that is what
   * the surface being replaced did. See F-D1-007.
   */
  it.fails("answers the block when its only window is closed", async () => {
    const { tab } = await openPause(promptEvent());
    expect(useAppStore.getState().interactivePrompt).not.toBeNull();

    act(() => {
      useAppStore.getState().closeTab(tab.id);
    });

    expect(useAppStore.getState().tabs.find((each) => each.id === tab.id)).toBeUndefined();
    expect(sentOfType("cancel_block")).toEqual([
      { type: "cancel_block", block_id: "node-1", workflow_id: "wf-prompt" },
    ]);
  });
});

/* -------------------------------------------------------------------------- */
/* Two pauses at once (spec §2 "Edge Cases")                                   */
/* -------------------------------------------------------------------------- */

describe("a second prompt while one is open", () => {
  /**
   * Proves: a second `interactive_prompt` makes the first pause tab
   * unanswerable, and the tab then tells the person the block is no longer
   * waiting — which is false; it is still paused.
   *
   * The store holds one `interactivePrompt`, and `setInteractivePrompt`
   * replaces it. `usePausePrompt` returns `null` for any tab whose
   * `pauseNodeId` is not the surviving prompt's block, so the first tab renders
   * "This block is no longer waiting for a decision", its Confirm is disabled
   * and its Cancel is enabled and does nothing.
   *
   * The single-prompt store is inherited, not new. What is new is that the spec
   * now promises otherwise: §2's edge case says *"a pause at an interactive
   * block opens its own Explore tab **beside this one**"*, and
   * `dispatchEvent.ts` says the point of the tab is that *"a person can now
   * leave it on screen and keep working in another tab"*. Two tabs beside each
   * other is the state this test constructs, and only one of them works.
   *
   * Why the existing tests did not: every case delivers one prompt. A modal
   * could only ever show one, so nothing in the suite it was carried from had a
   * reason to deliver two.
   *
   * Left failing. See F-D1-008.
   */
  it.fails("leaves the first pause answerable when a second block pauses", async () => {
    await openPause(promptEvent("node-1", "wf-prompt"));
    cleanup();

    // A second block, in another workflow, pauses while the first still waits.
    act(() => {
      dispatchWorkflowEvent(promptEvent("node-2", "wf-other"), deps);
    });
    expect(
      useAppStore.getState().tabs.filter((each) => each.kind === "explore"),
    ).toHaveLength(2);

    render(<ExploreTab tab={tabForBlock("node-1")} />);

    expect(screen.queryByTestId("explore-pause-resolved")).toBeNull();
    fireEvent.click(screen.getByTestId("explore-pause-cancel"));
    await act(async () => {
      await flush();
    });

    expect(sentOfType("cancel_block")).toEqual([
      { type: "cancel_block", block_id: "node-1", workflow_id: "wf-prompt" },
    ]);
  });

  /**
   * Proves: the second prompt's own tab works — a **negative result** that
   * bounds the finding above. The damage is confined to the pause that was
   * displaced; the newest one answers correctly, scoped to its own workflow.
   *
   * Why the existing tests did not: with one prompt per test, "the newest one
   * still works" is not a question that arises.
   */
  it("still answers the newest prompt, scoped to its own workflow", async () => {
    await openPause(promptEvent("node-1", "wf-prompt"));
    cleanup();
    const { seam, token } = await openPause(promptEvent("node-2", "wf-other"));
    await emit(seam, token, ROUTING_DECISION);

    fireEvent.click(screen.getByTestId("explore-pause-confirm"));
    await act(async () => {
      await flush();
    });

    expect(sentOfType("interactive_complete")).toEqual([
      {
        type: "interactive_complete",
        block_id: "node-2",
        workflow_id: "wf-other",
        data: { code: ROUTING_DECISION },
      },
    ]);
  });
});
