/**
 * ADR-054 spec 4 (T-001) — the Explore slice (FR-033, FR-034).
 *
 * Three things are proved here, and they are the three the spec asks for:
 *
 *   1. Every one of the nine session event types reaches the slice and changes
 *      it (FR-033).
 *   2. Events applied twice, and applied in the wrong order, reach the same
 *      state as one in-order pass — which is what makes it safe that the
 *      runtime publishes on its own threads and the socket is a second channel
 *      from the HTTP response.
 *   3. No mark, kernel state or binding is ever computed here (FR-034): a mark
 *      the runtime never sent does not appear, and a command reflected before
 *      its event is not reflected at all.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { EXPLORE_EVENT_TYPES } from "../../types/api";
import type {
  ExploreBindingsResponse,
  ExploreMarksResponse,
  ExploreSessionEventMessage,
  ExploreSessionResponse,
} from "../../types/api";
import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../index";

const SESSION_ID = "sess-1";
const PATH = "explore/analysis.ipynb";

function sessionResponse(overrides: Partial<ExploreSessionResponse> = {}): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: false,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [
      { cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] },
      { cell_id: "c2", cell_type: "code", source: "df.head()", enabled: true, marks: [] },
    ],
    ...overrides,
  };
}

function event(
  type: string,
  data: Record<string, unknown>,
  timestamp = "2026-09-05T10:00:00Z",
): ExploreSessionEventMessage {
  return { type, session_id: SESSION_ID, data, timestamp };
}

function held() {
  return useAppStore.getState().sessions[PATH];
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
});

describe("applyExploreSession", () => {
  it("writes the session from the response and indexes it by session id", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    expect(held().sessionId).toBe(SESSION_ID);
    expect(held().shellState).toBe("ready");
    expect(held().cells.map((cell) => cell.cellId)).toEqual(["c1", "c2"]);
    expect(useAppStore.getState().sessionPathById[SESSION_ID]).toBe(PATH);
  });

  it("is idempotent", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const first = held();
    useAppStore.getState().applyExploreSession(sessionResponse());
    expect(held()).toEqual(first);
  });

  it("reads never-run out of the runtime's mark rather than inferring it", () => {
    useAppStore.getState().applyExploreSession(
      sessionResponse({
        cells: [
          {
            cell_id: "c1",
            cell_type: "code",
            source: "x = 1",
            enabled: true,
            marks: ["never_run"],
          },
          { cell_id: "c2", cell_type: "code", source: "x + 1", enabled: true, marks: [] },
        ],
      }),
    );
    expect(held().cells[0].runState).toBe("never-run");
    expect(held().cells[1].runState).toBe("idle");
  });

  it("does not reset a run the events already reported", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore
      .getState()
      .applyExploreSessionEvent(event("explore.cell_state", { cell_id: "c1", state: "running" }));
    useAppStore.getState().applyExploreSession(sessionResponse());
    expect(held().cells[0].runState).toBe("running");
  });
});

describe("every session event reaches the slice (FR-033)", () => {
  beforeEach(() => {
    useAppStore.getState().applyExploreSession(sessionResponse());
  });

  it("covers the whole event set with a case each", () => {
    // A guard on the list itself: a new event type added to `api.ts` without a
    // case below fails here rather than silently going unhandled.
    expect([...EXPLORE_EVENT_TYPES]).toEqual([
      "explore.session_opened",
      "explore.session_closed",
      "explore.kernel_state",
      "explore.cell_state",
      "explore.cell_output",
      "explore.changed_names",
      "explore.analysis_updated",
      "explore.commit_recorded",
      "explore.packaged",
    ]);
  });

  it("session_opened records what the session was opened over", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.session_opened", {
        notebook_path: PATH,
        opened_over: "block_outputs",
        run_id: "run-9",
      }),
    );
    expect(held().openedOver).toBe("block_outputs");
  });

  it("session_closed closes the shell", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event("explore.session_closed", { notebook_path: PATH, branch_commit: "abc" }),
      );
    expect(held().shellState).toBe("closed");
  });

  it("kernel_state is copied verbatim, flag and state kept apart", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.kernel_state", {
        state: "dead",
        pid: null,
        memory_bytes: null,
        needs_restart: true,
      }),
    );
    expect(held().kernel.state).toBe("dead");
    expect(held().kernel.needsRestart).toBe(true);
  });

  it("cell_state writes the run state and the whole marks map", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event("explore.cell_state", { cell_id: "c1", state: "idle", marks: { c2: ["stale"] } }),
      );
    expect(held().cells[0].runState).toBe("idle");
    expect(held().cells[1].marks).toEqual(["stale"]);
  });

  it("cell_state clears a mark the runtime stopped sending", () => {
    const store = useAppStore.getState();
    store.applyExploreSessionEvent(
      event("explore.cell_state", { cell_id: "c1", state: "idle", marks: { c2: ["stale"] } }),
    );
    store.applyExploreSessionEvent(
      event(
        "explore.cell_state",
        { cell_id: "c2", state: "idle", marks: {} },
        "2026-09-05T10:00:01Z",
      ),
    );
    expect(held().cells[1].marks).toEqual([]);
  });

  it("cell_state names the reads that put a starting cell out of order", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event("explore.cell_state", { cell_id: "c2", state: "running", out_of_order: ["df"] }),
      );
    expect(held().cells[1].outOfOrderReads).toEqual([
      { name: "df", definer: null, last_binder: null },
    ]);
  });

  it("cell_output writes the MIME bundle and the execution count", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.cell_output", {
        cell_id: "c1",
        status: "ok",
        execution_count: 3,
        outputs: [{ output_type: "stream", name: "stdout", text: "hi" }],
      }),
    );
    expect(held().cells[0].outputs).toHaveLength(1);
    expect(held().cells[0].executionCount).toBe(3);
  });

  it("cell_output takes the runtime's error status, not a reading of the outputs", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.cell_output", {
        cell_id: "c1",
        status: "error",
        execution_count: 4,
        outputs: [{ output_type: "error", ename: "ValueError", evalue: "no", traceback: [] }],
      }),
    );
    expect(held().cells[0].runState).toBe("error");
  });

  it("changed_names writes the cell's changed set and the session's unobservables", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.changed_names", {
        cell_id: "c1",
        changed: ["df"],
        unobservable: ["conn"],
      }),
    );
    expect(held().cells[0].changedNames).toEqual(["df"]);
    expect(held().unobservableNames).toEqual(["conn"]);
  });

  it("analysis_updated records the reason the graph view reads", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event("explore.analysis_updated", { reason: "cell_ran", cell_id: "c1" }),
      );
    expect(held().lastAnalysisReason).toBe("cell_ran");
  });

  it("commit_recorded takes a branch commit as the notebook's version", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.commit_recorded", {
        sha: "deadbeef",
        ref: "branch",
        notebook_path: PATH,
      }),
    );
    expect(held().notebookCommit).toBe("deadbeef");
    // A per-run explore commit goes to its own ref and is not the version.
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event(
          "explore.commit_recorded",
          { sha: "cafe", ref: "refs/scistudio/explore", cell_id: "c1" },
          "2026-09-05T10:00:02Z",
        ),
      );
    expect(held().notebookCommit).toBe("deadbeef");
  });

  it("packaged records what packaging wrote", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.packaged", {
        block_name: "MyBlock",
        class_name: "MyBlockBlock",
        declaration_path: "blocks/my_block.py",
        notebook_path: "blocks/my_block.ipynb",
        notebook_commit: "abc",
        cells: ["c1"],
        on_new_input: "replay",
      }),
    );
    expect(held().lastPackaged?.block_name).toBe("MyBlock");
  });
});

describe("order and repetition do not change the answer", () => {
  beforeEach(() => {
    useAppStore.getState().applyExploreSession(sessionResponse());
  });

  it("applying the same event twice is applying it once", () => {
    const frame = event("explore.cell_state", {
      cell_id: "c1",
      state: "idle",
      marks: { c2: ["stale"] },
    });
    useAppStore.getState().applyExploreSessionEvent(frame);
    const once = held();
    useAppStore.getState().applyExploreSessionEvent(frame);
    expect(held()).toEqual(once);
  });

  it("a late-arriving older event does not undo a newer one", () => {
    const running = event(
      "explore.cell_state",
      { cell_id: "c1", state: "running" },
      "2026-09-05T10:00:00Z",
    );
    const idle = event(
      "explore.cell_state",
      { cell_id: "c1", state: "idle", marks: {} },
      "2026-09-05T10:00:05Z",
    );
    // In order.
    useAppStore.getState().applyExploreSessionEvent(running);
    useAppStore.getState().applyExploreSessionEvent(idle);
    const inOrder = held();

    // Reversed.
    useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore.getState().applyExploreSessionEvent(idle);
    useAppStore.getState().applyExploreSessionEvent(running);
    expect(held().cells[0].runState).toBe(inOrder.cells[0].runState);
    expect(held().cells[0].runState).toBe("idle");
  });

  it("an older marks map does not overwrite a newer one", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event(
          "explore.cell_state",
          { cell_id: "c1", state: "idle", marks: {} },
          "2026-09-05T10:00:05Z",
        ),
      );
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event(
          "explore.cell_state",
          { cell_id: "c2", state: "idle", marks: { c1: ["stale"] } },
          "2026-09-05T10:00:01Z",
        ),
      );
    expect(held().cells[0].marks).toEqual([]);
  });

  it("buffers events for a session whose path is not known yet, then drains them", () => {
    useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
    // The runtime publishes `session_opened` inside the open call, so an event
    // can reach the socket before the POST response reaches the caller.
    useAppStore
      .getState()
      .applyExploreSessionEvent(event("explore.cell_state", { cell_id: "c1", state: "running" }));
    expect(useAppStore.getState().sessions[PATH]).toBeUndefined();
    expect(useAppStore.getState().pendingExploreEvents[SESSION_ID]).toHaveLength(1);

    useAppStore.getState().applyExploreSession(sessionResponse());
    expect(held().cells[0].runState).toBe("running");
    expect(useAppStore.getState().pendingExploreEvents[SESSION_ID]).toBeUndefined();
  });

  it("drains the buffer when session_opened is what names the path", () => {
    useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
    useAppStore
      .getState()
      .applyExploreSessionEvent(event("explore.kernel_state", { state: "busy" }));
    useAppStore
      .getState()
      .applyExploreSessionEvent(
        event("explore.session_opened", { notebook_path: PATH, opened_over: "file" }),
      );
    expect(held().kernel.state).toBe("busy");
  });
});

describe("nothing is derived (FR-034)", () => {
  beforeEach(() => {
    useAppStore.getState().applyExploreSession(sessionResponse());
  });

  it("keeps only the runtime's three marks and invents none", () => {
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.cell_state", {
        cell_id: "c1",
        state: "idle",
        marks: { c1: ["stale", "not_a_mark"], c2: ["out_of_order"] },
      }),
    );
    expect(held().cells[0].marks).toEqual(["stale"]);
    expect(held().cells[1].marks).toEqual(["out_of_order"]);
  });

  it("marks no cell stale just because a cell below it ran", () => {
    // The runtime decides staleness. A run with no marks map leaves the marks
    // exactly as they were; the frontend never walks the graph itself.
    useAppStore.getState().applyExploreSessionEvent(
      event("explore.cell_output", {
        cell_id: "c1",
        status: "ok",
        execution_count: 1,
        outputs: [],
      }),
    );
    expect(held().cells[1].marks).toEqual([]);
  });

  it("copies a binding's liveness from the kernel rather than guessing it", () => {
    const bindings: ExploreBindingsResponse = {
      session_id: SESSION_ID,
      has_kernel: true,
      bindings: [
        {
          name: "df",
          exists_in_kernel: true,
          type_name: "Table",
          native_type_name: "DataFrame",
          last_bound_by: "c1",
        },
        { name: "model", exists_in_kernel: false },
      ],
    };
    useAppStore.getState().applyExploreBindings(SESSION_ID, bindings);
    expect(held().bindings.map((entry) => [entry.name, entry.live])).toEqual([
      ["df", true],
      ["model", false],
    ]);
    expect(held().bindings[1].typeName).toBeNull();
  });

  it("fills the out-of-order reasons from the marks response, not from the graph", () => {
    const marks: ExploreMarksResponse = {
      session_id: SESSION_ID,
      marks: [
        {
          cell_id: "c2",
          marks: ["out_of_order"],
          out_of_order_reads: [{ name: "df", definer: "c1", last_binder: "c3" }],
        },
      ],
      stale: [],
      out_of_order: ["c2"],
      never_run: [],
      last_bound_by: { df: "c3" },
    };
    useAppStore.getState().applyExploreMarks(SESSION_ID, marks);
    expect(held().cells[1].outOfOrderReads).toEqual([
      { name: "df", definer: "c1", last_binder: "c3" },
    ]);
    expect(held().cells[0].marks).toEqual([]);
  });

  it("only a run response may queue a cell, and it never demotes a running one", () => {
    useAppStore
      .getState()
      .applyExploreSessionEvent(event("explore.cell_state", { cell_id: "c1", state: "running" }));
    useAppStore.getState().applyExploreRunRequests(SESSION_ID, [
      { request_id: "r1", cell_id: "c1", kind: "cell", state: "queued" },
      { request_id: "r2", cell_id: "c2", kind: "cell", state: "queued" },
    ]);
    expect(held().cells[0].runState).toBe("running");
    expect(held().cells[1].runState).toBe("queued");
  });
});

describe("panels and pinning", () => {
  beforeEach(() => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore.getState().applyExploreBindings(SESSION_ID, {
      session_id: SESSION_ID,
      has_kernel: true,
      bindings: [{ name: "df", exists_in_kernel: true, type_name: "Table" }],
    });
  });

  it("records a mounted panel against its name and pins it when asked", () => {
    useAppStore.getState().noteExplorePanelOpened(SESSION_ID, {
      panelId: "p1",
      boundName: "df",
      pinned: true,
      frozen: false,
    });
    expect(held().panels).toHaveLength(1);
    expect(held().pinnedNames).toEqual(["df"]);
    expect(held().bindings[0].openPanelId).toBe("p1");
    expect(held().bindings[0].pinned).toBe(true);
  });

  it("unpins and closes without touching the other entries", () => {
    const store = useAppStore.getState();
    store.noteExplorePanelOpened(SESSION_ID, {
      panelId: "p1",
      boundName: "df",
      pinned: true,
      frozen: false,
    });
    store.setExplorePanelPinned(SESSION_ID, "p1", false);
    expect(held().pinnedNames).toEqual([]);
    store.noteExplorePanelClosed(SESSION_ID, "p1");
    expect(held().panels).toEqual([]);
    expect(held().bindings[0].openPanelId).toBeNull();
  });
});

describe("opening and failing", () => {
  it("records an open in flight and the refusal that ends it", () => {
    const store = useAppStore.getState();
    store.noteExploreSessionOpening(PATH);
    expect(held().shellState).toBe("opening");
    store.noteExploreSessionFailed(PATH, "Nothing to explore");
    expect(held().shellState).toBe("failed");
    expect(held().error).toBe("Nothing to explore");
  });

  it("forgets a session and its id index together", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore.getState().forgetExploreSession(PATH);
    expect(useAppStore.getState().sessions[PATH]).toBeUndefined();
    expect(useAppStore.getState().sessionPathById[SESSION_ID]).toBeUndefined();
  });
});
