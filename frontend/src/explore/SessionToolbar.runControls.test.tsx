/**
 * ADR-054 spec 4 (T-006, T-007) — the toolbar's run controls (FR-013, FR-014,
 * FR-016, FR-034; SC-004).
 *
 * A separate file from `SessionToolbar.test.tsx` on purpose: the toolbar is
 * shared by three agents in this assembly — the kernel list and package are
 * S4-A4's, confirm and cancel are S4-A3's — and each half's evidence should be
 * readable and reviewable on its own.
 *
 * The whole toolbar is rendered rather than the region alone, so what is proved
 * is that the controls are really on the toolbar a person sees.
 *
 * Every test asserts two things: that the control sent its command, **and that
 * it sent nothing else**. "Send nothing the person did not ask for" (FR-013) is
 * not observable from one assertion at a time.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import type { ExploreTab as ExploreTabState } from "../store/types";
import type { ExploreSessionResponse } from "../types/api";

import { SessionToolbar } from "./SessionToolbar";

const runExploreStale = vi.fn();
const interruptExploreSession = vi.fn();
const restartExploreSession = vi.fn();
const commitExploreSession = vi.fn();

const commands = {
  runExploreStale,
  interruptExploreSession,
  restartExploreSession,
  commitExploreSession,
};

vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    runExploreStale: (...args: unknown[]) => runExploreStale(...args),
    interruptExploreSession: (...args: unknown[]) => interruptExploreSession(...args),
    restartExploreSession: (...args: unknown[]) => restartExploreSession(...args),
    commitExploreSession: (...args: unknown[]) => commitExploreSession(...args),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-toolbar";

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
    cells: [
      { cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] },
      { cell_id: "c2", cell_type: "code", source: "print(df)", enabled: true, marks: [] },
      { cell_id: "c3", cell_type: "code", source: "plot(df)", enabled: true, marks: [] },
    ],
  };
}

function markStale(cellIds: string[]) {
  useAppStore.getState().applyExploreSessionEvent({
    type: "explore.cell_state",
    session_id: SESSION_ID,
    data: { marks: Object.fromEntries(cellIds.map((cellId) => [cellId, ["stale"]])) },
    timestamp: "2026-09-05T12:00:00Z",
  });
}

function renderToolbar() {
  const session = useAppStore.getState().sessions[PATH];
  return render(
    <SessionToolbar
      graphVisible={false}
      onToggleGraph={vi.fn()}
      onToggleNotebook={vi.fn()}
      session={session}
      tab={tab()}
    />,
  );
}

/** Assert that exactly one command was sent, and say which when it was not. */
function onlyCommandSent(name: keyof typeof commands) {
  for (const [key, spy] of Object.entries(commands)) {
    if (key === name) expect(spy).toHaveBeenCalledTimes(1);
    else expect(spy, `${key} should not have been called`).not.toHaveBeenCalled();
  }
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
  for (const spy of Object.values(commands)) spy.mockReset();
  runExploreStale.mockResolvedValue({ session_id: SESSION_ID, requests: [] });
  interruptExploreSession.mockResolvedValue({
    session_id: SESSION_ID,
    state: "idle",
    pid: 1,
    memory_bytes: null,
    needs_restart: false,
  });
  restartExploreSession.mockResolvedValue({
    session_id: SESSION_ID,
    state: "starting",
    pid: 2,
    memory_bytes: null,
    needs_restart: false,
  });
  commitExploreSession.mockResolvedValue({ session_id: SESSION_ID, sha: "abc123" });
  useAppStore.getState().applyExploreSession(sessionResponse());
});

afterEach(cleanup);

describe("run-stale carries the count the runtime reported (FR-013)", () => {
  it("shows the stale count and sends only run-stale", async () => {
    markStale(["c2", "c3"]);
    renderToolbar();
    expect(screen.getByTestId("explore-toolbar-run-controls").dataset.staleCount).toBe("2");
    expect(screen.getByTestId("explore-run-stale").textContent).toBe("Run stale (2)");

    fireEvent.click(screen.getByTestId("explore-run-stale"));
    await waitFor(() => expect(runExploreStale).toHaveBeenCalledWith(SESSION_ID));
    onlyCommandSent("runExploreStale");
  });

  it("is refused when the runtime has marked nothing stale", () => {
    renderToolbar();
    const control = screen.getByTestId("explore-run-stale") as HTMLButtonElement;
    expect(control.textContent).toBe("Run stale (0)");
    expect(control.disabled).toBe(true);
    fireEvent.click(control);
    expect(runExploreStale).not.toHaveBeenCalled();
  });

  it("writes the queued requests the response reported, and nothing before it", async () => {
    markStale(["c2"]);
    runExploreStale.mockResolvedValue({
      session_id: SESSION_ID,
      requests: [{ request_id: "r1", cell_id: "c2", kind: "cell", state: "queued" }],
    });
    renderToolbar();
    fireEvent.click(screen.getByTestId("explore-run-stale"));
    // Nothing is written on the click itself; the response is what writes.
    expect(useAppStore.getState().sessions[PATH].cells[1].runState).toBe("idle");
    await waitFor(() =>
      expect(useAppStore.getState().sessions[PATH].cells[1].runState).toBe("queued"),
    );
  });
});

describe("interrupt, restart and commit (FR-014)", () => {
  it.each([
    ["explore-interrupt", "interruptExploreSession"],
    ["explore-restart", "restartExploreSession"],
    ["explore-commit", "commitExploreSession"],
  ] as const)("%s sends exactly its own command", async (testId, name) => {
    renderToolbar();
    fireEvent.click(screen.getByTestId(testId));
    await waitFor(() => expect(commands[name]).toHaveBeenCalledWith(SESSION_ID));
    onlyCommandSent(name);
  });

  it("reflects none of them until the runtime's event arrives (FR-034)", async () => {
    renderToolbar();
    fireEvent.click(screen.getByTestId("explore-restart"));
    await waitFor(() => expect(restartExploreSession).toHaveBeenCalled());
    // The response said "starting"; the slice still holds what the events said,
    // because a command is reflected by its event and not by its response.
    expect(useAppStore.getState().sessions[PATH].kernel.state).toBe("not-started");

    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "starting", needs_restart: false },
      timestamp: "2026-09-05T12:00:02Z",
    });
    expect(useAppStore.getState().sessions[PATH].kernel.state).toBe("starting");
  });

  it("shows the refusal when a command fails, and sends nothing else", async () => {
    interruptExploreSession.mockRejectedValueOnce(new Error("no kernel is running"));
    renderToolbar();
    fireEvent.click(screen.getByTestId("explore-interrupt"));
    const message = await screen.findByTestId("explore-run-controls-error");
    expect(message.textContent).toContain("no kernel is running");
    onlyCommandSent("interruptExploreSession");
  });
});

describe("the kernel's state and the restart offer (FR-016)", () => {
  it("offers a restart when the runtime reports the kernel dead", () => {
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "dead", needs_restart: false },
      timestamp: "2026-09-05T12:00:03Z",
    });
    renderToolbar();
    expect(screen.getByTestId("explore-toolbar-kernel-state").textContent).toBe("dead");
    expect(screen.getByTestId("explore-kernel-restart-offer")).toBeTruthy();
  });

  it("offers a restart when a branch change retires the kernel", () => {
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "idle", needs_restart: true },
      timestamp: "2026-09-05T12:00:04Z",
    });
    renderToolbar();
    expect(screen.getByTestId("explore-toolbar-kernel-state").textContent).toBe("needs restart");
    expect(screen.getByTestId("explore-kernel-restart-offer")).toBeTruthy();
  });

  it("makes no offer while the kernel is well", () => {
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.kernel_state",
      session_id: SESSION_ID,
      data: { state: "idle", needs_restart: false },
      timestamp: "2026-09-05T12:00:05Z",
    });
    renderToolbar();
    expect(screen.queryByTestId("explore-kernel-restart-offer")).toBeNull();
  });
});

describe("before the session lands", () => {
  it("refuses every control rather than sending to a session that has no id", () => {
    useAppStore.setState({ sessions: {}, sessionPathById: {} });
    render(
      <SessionToolbar
        graphVisible={false}
        onToggleGraph={vi.fn()}
        onToggleNotebook={vi.fn()}
        session={undefined}
        tab={tab()}
      />,
    );
    for (const testId of [
      "explore-run-stale",
      "explore-interrupt",
      "explore-restart",
      "explore-commit",
    ]) {
      const control = screen.getByTestId(testId) as HTMLButtonElement;
      expect(control.disabled).toBe(true);
      fireEvent.click(control);
    }
    for (const spy of Object.values(commands)) expect(spy).not.toHaveBeenCalled();
  });
});
