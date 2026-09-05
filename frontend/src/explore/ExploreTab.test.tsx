/**
 * ADR-054 spec 4 (T-002) — the Explore tab's layout (FR-005 to FR-007).
 *
 * The tab occupies two columns, so the four regions the spec names are split
 * across the two components this module exports: the toolbar, the strip and
 * the panel host are the centre, and the notebook pane is the right column.
 * Both are rendered here, which is what "the layout renders the four regions"
 * means for a tab that is not one box.
 *
 * FR-006 is proved by rendering the centre with no notebook pane at all: the
 * right pane collapsing is the workspace's `ResizablePanel` doing what it does
 * for the preview today, and what has to be true of *this* component is that
 * the toolbar and the panels are still there when the notebook is not.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../testUtils";
import type { ExploreSessionResponse } from "../types/api";
import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState } from "../store/types";

import { ExploreNotebookPane, ExploreTab } from "./ExploreTab";

const openExploreSession = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    openExploreSession: (...args: unknown[]) => openExploreSession(...args),
    /*
     * ADR-054 spec 4 T-009 (S4-A3): a mounted panel slot reads its variable
     * through the session API as soon as it is on screen. These layout tests
     * assert only that a slot exists per open panel, so the read is stubbed to
     * an empty envelope rather than driven; `PanelSlots.test.tsx` owns what a
     * slot does with the answer.
     */
    windowExploreVariable: () =>
      Promise.resolve({ session_id: "sess-tab", name: "", envelope: {} }),
    /* The variable strip re-reads the bindings whenever the analysis moves. */
    getExploreBindings: () =>
      Promise.resolve({ session_id: "sess-tab", has_kernel: true, bindings: [] }),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-tab";

function tab(overrides: Partial<ExploreTabState> = {}): ExploreTabState {
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
    ...overrides,
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

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  openExploreSession.mockReset();
  openExploreSession.mockResolvedValue(sessionResponse());
});

// The runner does not enable RTL global cleanup, so each render is unmounted
// here; without it the second render of a test file finds two of everything.
afterEach(cleanup);

describe("the four regions (FR-005)", () => {
  it("renders the toolbar, the strip and the panel host in the centre", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-session-toolbar")).toBeTruthy();
    expect(screen.getByTestId("explore-variable-strip-region")).toBeTruthy();
    expect(screen.getByTestId("explore-panel-host")).toBeTruthy();
  });

  it("renders the notebook region in the right column", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreNotebookPane tab={tab()} />);
    expect(screen.getByTestId("explore-notebook-pane")).toBeTruthy();
    expect(screen.getByTestId("explore-notebook-region")).toBeTruthy();
  });

  it("shows the toolbar before the session lands, so the tab is never blank", () => {
    render(<ExploreTab tab={tab({ sessionId: SESSION_ID })} />);
    expect(screen.getByTestId("explore-session-toolbar")).toBeTruthy();
    expect(screen.getByTestId("explore-toolbar-kernel-state").textContent).toBe("opening");
  });
});

describe("the centre stays usable with the notebook away (FR-006)", () => {
  it("keeps the toolbar and the panel host when the notebook pane is hidden", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const hidden = tab({ notebookVisible: false });
    const pane = render(<ExploreNotebookPane tab={hidden} />);
    // The right column renders nothing, exactly as a collapsed preview does.
    expect(pane.container.innerHTML).toBe("");
    pane.unmount();

    render(<ExploreTab tab={hidden} />);
    expect(screen.getByTestId("explore-session-toolbar")).toBeTruthy();
    expect(screen.getByTestId("explore-panel-host")).toBeTruthy();
  });

  it("toggles the notebook pane from the toolbar", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const target = tab();
    useAppStore.setState({ tabs: [target], activeTabId: target.id });
    render(<ExploreTab tab={target} />);
    fireEvent.click(screen.getByTestId("explore-toolbar-notebook-toggle"));
    const stored = useAppStore.getState().tabs[0];
    expect(stored.kind === "explore" && stored.notebookVisible).toBe(false);
  });
});

describe("the panel host holds more than one panel (FR-007)", () => {
  it("mounts one slot per open panel so two can be compared", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const store = useAppStore.getState();
    store.noteExplorePanelOpened(SESSION_ID, {
      panelId: "p1",
      boundName: "df",
      pinned: false,
      frozen: false,
    });
    store.noteExplorePanelOpened(SESSION_ID, {
      panelId: "p2",
      boundName: "model",
      pinned: false,
      frozen: false,
    });
    render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-panel-slot-p1")).toBeTruthy();
    expect(screen.getByTestId("explore-panel-slot-p2")).toBeTruthy();
    // The arrangement is a two-column grid, which is what makes them
    // comparable rather than stacked.
    expect(screen.getByTestId("explore-panel-host").className).toContain("md:grid-cols-2");
  });

  it("says what to do when nothing is mounted yet", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-panel-host-empty")).toBeTruthy();
  });

  it("shows the refusal that failed the open in place of the panels", () => {
    useAppStore.getState().noteExploreSessionFailed(PATH, "This block has nothing to explore.");
    render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-panel-host-empty").textContent).toBe(
      "This block has nothing to explore.",
    );
  });
});

describe("the secondary graph view (FR-032)", () => {
  it("swaps the panel host for the graph and back", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreTab tab={tab()} />);
    expect(screen.queryByTestId("explore-graph-region")).toBeNull();
    fireEvent.click(screen.getByTestId("explore-toolbar-graph-toggle"));
    expect(screen.getByTestId("explore-graph-region")).toBeTruthy();
    expect(screen.queryByTestId("explore-panel-host")).toBeNull();
    fireEvent.click(screen.getByTestId("explore-toolbar-graph-toggle"));
    expect(screen.getByTestId("explore-panel-host")).toBeTruthy();
  });
});

describe("pause mode (FR-024, FR-026)", () => {
  it("offers confirm and cancel and hides the notebook pane", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const paused = tab({ mode: "pause", notebookVisible: false, pauseNodeId: "node-3" });
    render(<ExploreTab tab={paused} />);
    expect(screen.getByTestId("explore-toolbar-pause-controls")).toBeTruthy();
    expect(screen.getByTestId("explore-toolbar-notebook-toggle").textContent).toBe("Open notebook");
  });

  it("shows no pause controls in a session tab", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreTab tab={tab()} />);
    expect(screen.queryByTestId("explore-toolbar-pause-controls")).toBeNull();
  });
});

describe("restore on reload (FR-001)", () => {
  it("re-fetches the session state for a rehydrated tab", async () => {
    const restored = tab({ sessionId: null, restoring: true });
    useAppStore.setState({ tabs: [restored], activeTabId: restored.id });
    render(<ExploreTab tab={restored} />);
    // The restore reopens the notebook by path — the tab kept nothing else.
    await vi.waitFor(() => {
      expect(openExploreSession).toHaveBeenCalledWith({ source: "notebook", path: PATH });
    });
    await vi.waitFor(() => {
      expect(useAppStore.getState().sessions[PATH]?.shellState).toBe("ready");
    });
    const stored = useAppStore.getState().tabs[0];
    expect(stored.kind === "explore" && stored.sessionId).toBe(SESSION_ID);
  });

  it("does not re-fetch a tab that already has its session", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    render(<ExploreTab tab={tab()} />);
    expect(openExploreSession).not.toHaveBeenCalled();
  });

  it("records the refusal when the restore fails", async () => {
    openExploreSession.mockRejectedValueOnce(new Error("notebook is gone"));
    const restored = tab({ sessionId: null, restoring: true });
    useAppStore.setState({ tabs: [restored], activeTabId: restored.id });
    render(<ExploreTab tab={restored} />);
    await vi.waitFor(() => {
      expect(useAppStore.getState().sessions[PATH]?.shellState).toBe("failed");
    });
    expect(useAppStore.getState().sessions[PATH].error).toBe("notebook is gone");
  });
});

describe("the kernel is shown, never inferred (FR-016, FR-034)", () => {
  it("renders the runtime's state, and its needs-restart flag over it", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "busy", needs_restart: false },
      timestamp: "2026-09-05T11:00:00Z",
    });
    const { unmount } = render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-toolbar-kernel-state").textContent).toBe("busy");
    unmount();

    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "dead", needs_restart: true },
      timestamp: "2026-09-05T11:00:05Z",
    });
    render(<ExploreTab tab={tab()} />);
    expect(screen.getByTestId("explore-toolbar-kernel-state").textContent).toBe("needs restart");
    // The slice still holds what the runtime said; only the label collapses.
    expect(useAppStore.getState().sessions[PATH].kernel.state).toBe("dead");
  });
});
