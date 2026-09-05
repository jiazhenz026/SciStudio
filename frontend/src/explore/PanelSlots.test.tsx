/**
 * ADR-054 spec 4 (T-009) — one mounted panel over one variable.
 *
 * The four properties FR-021 to FR-023 turn on are asserted here, and three of
 * them are asserted through a real frame rather than by calling a handler: an
 * emission that reaches the session API has to have crossed the panel message
 * contract first, and a test that called `onEmit` directly would pass with the
 * capability gate wired backwards.
 *
 * The fourth — that only bound panels refresh — is deliberately driven without
 * a frame. What is under test there is which *reads* the shell issues after a
 * changed-names event, and mounting two frames to observe two `fetch`-shaped
 * facts would only add ways for the test to be flaky.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import type { RealFrameSeam } from "../panels/__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "../panels/__tests__/support";
import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState, PanelSlot } from "../store/types";
import { resetAppStore } from "../testUtils";
import type {
  ExploreBindingsResponse,
  ExploreSessionResponse,
  PanelDescriptorResponse,
} from "../types/api";

import { ExplorePanelSlot, forgetSlotDescriptors, rememberSlotDescriptor } from "./PanelSlots";

const windowExploreVariable = vi.fn();
const emitExploreSnippet = vi.fn();
const readExploreCells = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    windowExploreVariable: (...args: unknown[]) => windowExploreVariable(...args),
    emitExploreSnippet: (...args: unknown[]) => emitExploreSnippet(...args),
    readExploreCells: (...args: unknown[]) => readExploreCells(...args),
  },
}));

const listPanels = vi.fn();
vi.mock("../lib/api/data", () => ({
  dataApi: {
    listPanels: (...args: unknown[]) => listPanels(...args),
    listPanelChoices: () => Promise.resolve({ choices: [] }),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-slots";
const PANEL_ID = "core.dataframe.editor";
const SLOT_ID = `df::${PANEL_ID}`;

/** Verbatim from the shipped `core.interactive.data_router` document's form. */
const EMISSION = "df = df.drop(index=[3, 7])\nscistudio.output(df=df)";

const DESCRIPTOR: PanelDescriptorResponse = {
  panel_id: PANEL_ID,
  display_name: PANEL_ID,
  api_version: "1",
  accepted_api_version: "1",
  capability: "producing",
  document_url: `/api/panels/assets/${PANEL_ID}/index.html`,
  asset_base_url: `/api/panels/assets/${PANEL_ID}/`,
  read_limits: { max_rows: 100, max_bytes: 1000 },
};

function tab(): ExploreTabState {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: SESSION_ID,
    displayName: "analysis.ipynb",
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
  };
}

function sessionResponse(): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: true,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [{ cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] }],
  };
}

function bindings(): ExploreBindingsResponse {
  return {
    session_id: SESSION_ID,
    has_kernel: true,
    bindings: [
      { name: "df", exists_in_kernel: true, type_name: "DataFrame" },
      { name: "other", exists_in_kernel: true, type_name: "DataFrame" },
    ],
  };
}

function slot(overrides: Partial<PanelSlot> = {}): PanelSlot {
  return { panelId: SLOT_ID, boundName: "df", pinned: false, frozen: false, ...overrides };
}

function currentSession() {
  return useAppStore.getState().sessions[PATH];
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  forgetSlotDescriptors();
  windowExploreVariable.mockReset();
  windowExploreVariable.mockResolvedValue({
    session_id: SESSION_ID,
    name: "df",
    envelope: { previewer_id: PANEL_ID, kind: "dataframe", payload: {} },
  });
  emitExploreSnippet.mockReset();
  readExploreCells.mockReset();
  listPanels.mockReset();
  listPanels.mockResolvedValue({ panels: [], diagnostics: [] });
  useAppStore.getState().applyExploreSession(sessionResponse());
  useAppStore.getState().applyExploreBindings(SESSION_ID, bindings());
});

afterEach(cleanup);

/** Mount one slot with a real frame and drive it through the handshake. */
async function mountSlot(theSlot: PanelSlot = slot()) {
  rememberSlotDescriptor(theSlot.panelId, DESCRIPTOR);
  const seam = createRealFrameSeam();
  render(
    <ExplorePanelSlot
      tab={tab()}
      session={currentSession()}
      slot={theSlot}
      frameFactory={seam.factory}
    />,
  );
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
  return { seam, token };
}

async function emit(seam: RealFrameSeam, token: string, code: string) {
  await act(async () => {
    seam.fromPanel(token, "emit", { code });
    await flush();
  });
}

describe("an emission the session accepts (FR-021)", () => {
  it("names the panel, and the accepted cell lands after the current one, queued", async () => {
    emitExploreSnippet.mockResolvedValue({
      session_id: SESSION_ID,
      cell_id: "c2",
      request: {
        request_id: "r1",
        cell_id: "c2",
        kind: "snippet",
        state: "queued",
        panel: PANEL_ID,
      },
    });
    readExploreCells.mockResolvedValue({
      session_id: SESSION_ID,
      cells: [
        { cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] },
        { cell_id: "c2", cell_type: "code", source: EMISSION, enabled: true, marks: [] },
      ],
    });

    const { seam, token } = await mountSlot();
    await emit(seam, token, EMISSION);

    // The emission is sent naming the panel and the name it is bound to; the
    // shell does not interpret the code (FR-012 puts that in the backend).
    await waitFor(() =>
      expect(emitExploreSnippet).toHaveBeenCalledWith(SESSION_ID, {
        source: EMISSION,
        panel: PANEL_ID,
        bound_names: ["df"],
      }),
    );

    await waitFor(() => expect(currentSession().cells).toHaveLength(2));
    const [first, second] = currentSession().cells;
    expect(first.cellId).toBe("c1");
    // After the current cell, and queued — the run response is the only door a
    // cell reaches `queued` through.
    expect(second.cellId).toBe("c2");
    expect(second.runState).toBe("queued");
  });
});

describe("an emission the session refuses (FR-021)", () => {
  it("shows the refusal naming the panel and the statement, and inserts nothing", async () => {
    const refusal =
      `Panel '${PANEL_ID}' emitted an expression on line 1, which a session will not run: ` +
      `'df.drop(index=[3], inplace=True)'. It is refused rather than rewritten.`;
    emitExploreSnippet.mockRejectedValue(new ApiError(refusal, 422));

    const { seam, token } = await mountSlot();
    await emit(seam, token, "df.drop(index=[3], inplace=True)");

    const note = await screen.findByTestId(`explore-panel-note-${SLOT_ID}`);
    expect(note.getAttribute("data-note-kind")).toBe("refused");
    expect(note.getAttribute("data-note-panel")).toBe(PANEL_ID);
    expect(note.textContent).toContain(PANEL_ID);
    expect(note.textContent).toContain("df.drop(index=[3], inplace=True)");

    // Nothing was inserted: the notebook is exactly what it was.
    expect(readExploreCells).not.toHaveBeenCalled();
    expect(currentSession().cells).toHaveLength(1);
  });
});

describe("the freeze while a cell runs (FR-023)", () => {
  it("refuses the submission with a note and keeps the panel reading", async () => {
    // The runtime's own changed set for the running cell, and the runtime's own
    // statement that it is running. Neither is worked out here.
    useAppStore.getState().applyExploreGraph(SESSION_ID, {
      session_id: SESSION_ID,
      cells: ["c1"],
      edges: [],
      unresolved_reads: [],
      unknown_binding_cells: [],
      changed_sets: { c1: ["df"] },
    });
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.cell_state",
      session_id: SESSION_ID,
      data: { cell_id: "c1", state: "running", out_of_order: [] },
      timestamp: "2026-09-05T12:00:00Z",
    });

    const { seam, token } = await mountSlot();
    expect(screen.getByTestId(`explore-panel-slot-${SLOT_ID}`).getAttribute("data-frozen")).toBe(
      "true",
    );

    await emit(seam, token, EMISSION);

    const note = await screen.findByTestId(`explore-panel-note-${SLOT_ID}`);
    expect(note.getAttribute("data-note-kind")).toBe("frozen");
    expect(note.textContent).toContain("df");
    // Refused by the shell: nothing was sent.
    expect(emitExploreSnippet).not.toHaveBeenCalled();

    // And reading continues — the panel's bounded read is answered as usual.
    windowExploreVariable.mockClear();
    await act(async () => {
      seam.fromPanel(token, "read", { request_id: "read-1", query: { page: 2 } });
      await flush();
    });
    await waitFor(() =>
      expect(windowExploreVariable).toHaveBeenCalledWith(SESSION_ID, {
        name: "df",
        query: { page: 2 },
      }),
    );
  });
});

/**
 * Two slots that stay mounted across the event, reading the session out of the
 * store the way the tab does. Staying mounted is the point: a remount would
 * re-read both panels and prove nothing about which one the event reached.
 */
function TwoSlots() {
  const session = useAppStore((state) => state.sessions[PATH]);
  return (
    <>
      <ExplorePanelSlot tab={tab()} session={session} slot={slot()} />
      <ExplorePanelSlot
        tab={tab()}
        session={session}
        slot={slot({ panelId: `other::${PANEL_ID}`, boundName: "other" })}
      />
    </>
  );
}

describe("the changed-names refresh (FR-022)", () => {
  it("re-reads only the panels bound to the names that changed", async () => {
    render(<TwoSlots />);
    await waitFor(() => expect(windowExploreVariable).toHaveBeenCalledTimes(2));
    windowExploreVariable.mockClear();

    // A run ended and the runtime says which names moved.
    await act(async () => {
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.changed_names",
        session_id: SESSION_ID,
        data: { cell_id: "c1", changed: ["df"], unobservable: [] },
        timestamp: "2026-09-05T12:00:01Z",
      });
      await flush(3);
    });

    await waitFor(() => expect(windowExploreVariable).toHaveBeenCalledTimes(1));
    expect(windowExploreVariable).toHaveBeenCalledWith(SESSION_ID, { name: "df" });
    const names = windowExploreVariable.mock.calls.map(
      (call) => (call[1] as { name: string }).name,
    );
    // The panel bound to a name the run did not change was left alone.
    expect(names).not.toContain("other");
  });
});
