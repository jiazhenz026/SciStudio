/**
 * ADR-054 spec 4 — adversarial tests against the Explore slice (S4-D1, #2253).
 *
 * The slice already has a suite (`exploreSlice.test.ts`) and it passes. This
 * file is the other half: the cases that suite was shaped not to ask.
 *
 * Spec §4.5 makes two claims this file attacks directly.
 *
 *   1. *"Two sources of truth for marks. A frontend that recomputed marks from
 *      the graph would disagree with the runtime in exactly the ambiguous
 *      cases. FR-034 forbids it, and the slice is written only from events and
 *      responses."* — Not recomputing is only half of FR-034. The other half is
 *      that what is on screen must **still be** what the runtime last said, and
 *      a slice that ignores part of an event holds a stale answer just as
 *      surely as one that computed a wrong answer.
 *   2. *"Events out of order. A cell-state event may arrive before the response
 *      to the command that caused it. The slice applies events idempotently by
 *      cell id and state, so order does not matter."* — Idempotence is not
 *      order-independence, and the claim is only true of the three appliers
 *      that carry a watermark. The rest are last-write-wins.
 *
 * The existing suite proves order-independence for `cell_state`, `cell_output`
 * and the marks map, which are exactly the three appliers that guard against
 * it. It asserts nothing about `changed_names`, `commit_recorded`,
 * `session_opened` / `session_closed`, about an event whose session id is no
 * longer the session on screen, or about what a `kernel_state` event does to
 * the cells whose namespace the kernel took with it.
 *
 * **A failing test here is the deliverable.** Each one names the finding it
 * proves in `docs/planning/adr-054-assembly-followups.md` under
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

import { beforeEach, describe, expect, it } from "vitest";

import { frozenNamesOf, panelRefreshKey } from "../../explore/PanelSlots";
import type { ExploreSessionEventMessage, ExploreSessionResponse } from "../../types/api";
import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../index";

const SESSION_ID = "sess-adv-1";
const PATH = "explore/adversarial.ipynb";

function sessionResponse(overrides: Partial<ExploreSessionResponse> = {}): ExploreSessionResponse {
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
      { cell_id: "c2", cell_type: "code", source: "df.head()", enabled: true, marks: [] },
    ],
    ...overrides,
  };
}

function event(
  type: string,
  data: Record<string, unknown>,
  timestamp = "2026-09-05T10:00:00Z",
  sessionId = SESSION_ID,
): ExploreSessionEventMessage {
  return { type, session_id: sessionId, data, timestamp };
}

function apply(message: ExploreSessionEventMessage) {
  useAppStore.getState().applyExploreSessionEvent(message);
}

function held(path = PATH) {
  return useAppStore.getState().sessions[path];
}

function cell(cellId: string, path = PATH) {
  const found = held(path)?.cells.find((candidate) => candidate.cellId === cellId);
  if (!found) throw new Error(`no cell ${cellId} in ${path}`);
  return found;
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
});

/* -------------------------------------------------------------------------- */
/* FR-034 — the screen must hold the runtime's answer, not a superseded one    */
/* -------------------------------------------------------------------------- */

describe("a kernel that goes away takes its cell states with it (FR-034)", () => {
  /**
   * Proves: after the runtime restarts the kernel and says every cell is
   * `never_run`, the slice still shows the cell that was running as `running`.
   *
   * Why the existing tests did not: `exploreSlice.test.ts` asserts that a
   * `cell_state` marks map is copied verbatim ("cell_state writes the run state
   * and the whole marks map") and that a cleared mark actually clears, but it
   * only ever sends a marks map to a cell that was resting. It never sends the
   * restart shape — `{reason: "kernel_restarted", marks: {...}}` with **no cell
   * id**, which is the one `ExploreSession.restart_kernel` publishes — to a
   * session with a cell in flight, so nothing asked what happens to
   * `CellView.runState` when the namespace behind it is thrown away.
   *
   * The slice already owns the mapping this needs: `restingRunState` reads the
   * runtime's own `never_run` mark and is documented as "the runtime's own
   * statement", so honouring it here is not a derivation FR-034 forbids — it is
   * the same copy the response path already makes.
   */
  it.fails("shows a cell the runtime now calls never-run as never-run, not as running", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(event("explore.cell_state", { cell_id: "c1", state: "running" }, "2026-09-05T10:00:00Z"));
    expect(cell("c1").runState).toBe("running");

    // `ExploreSession.restart_kernel` — a `kernel_state`, then a `cell_state`
    // with no cell id whose marks map is `_reset_marks_to_never_run`'s output.
    apply(
      event(
        "explore.kernel_state",
        { state: "idle", needs_restart: false },
        "2026-09-05T10:00:05Z",
      ),
    );
    apply(
      event(
        "explore.cell_state",
        { reason: "kernel_restarted", marks: { c1: ["never_run"], c2: ["never_run"] } },
        "2026-09-05T10:00:05Z",
      ),
    );

    expect(cell("c1").marks).toEqual(["never_run"]);
    // The runtime says this cell has never run in this kernel. The shell is
    // still drawing "running" over it.
    expect(cell("c1").runState).toBe("never-run");
  });

  /**
   * Proves: FR-023's submission freeze never lifts after a kernel restart,
   * because the freeze is keyed on `runState === "running"` and the restart
   * leaves that state behind.
   *
   * Why the existing tests did not: `PanelSlots.test.tsx` proves the freeze
   * engages while a cell runs and that reading continues, and it lifts the
   * freeze in its fixtures by writing an idle `cell_state`. Nothing drives the
   * two ways a run ends without one — a restart and a death — so nothing asked
   * whether the freeze can be left permanently on.
   *
   * This is the user-visible half of the finding above: every panel bound to a
   * name the interrupted cell would have changed is refused for the rest of the
   * session, and the note it shows says "try again when the run ends" for a run
   * that already ended.
   */
  it.fails("lifts the panel freeze when the run the kernel was doing is gone", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(event("explore.cell_state", { cell_id: "c1", state: "running" }));
    apply(event("explore.changed_names", { cell_id: "c1", changed: ["df"], unobservable: [] }));
    expect(frozenNamesOf(held())).toContain("df");

    apply(
      event(
        "explore.cell_state",
        { reason: "kernel_restarted", marks: { c1: ["never_run"], c2: ["never_run"] } },
        "2026-09-05T10:00:05Z",
      ),
    );

    expect([...frozenNamesOf(held())]).toEqual([]);
  });

  /**
   * Proves: when the kernel dies, the marks the runtime threw away stay on
   * screen.
   *
   * Why the existing tests did not: the slice suite asserts `kernel_state` is
   * "copied verbatim, flag and state kept apart" — which it is — and stops
   * there. It never checks what the rest of the session looks like afterwards.
   *
   * **The fix for this one is not in the frontend.**
   * `ExploreSession.report_kernel_died` (`src/scistudio/explore/session.py`)
   * calls `_reset_marks_to_never_run()` and then emits **only**
   * `KERNEL_STATE {state: "dead", needs_restart: true}` — no marks payload —
   * where `restart_kernel` emits `kernel_state` *and* a `cell_state` carrying
   * `_marks_payload()`. `stop_kernel` has the same shape, so ending a kernel
   * from FR-015's kernel list does it too. The frontend cannot honour a mark
   * reset it is never told about without deriving one, which FR-034 forbids, so
   * this test is left failing against the event stream as it is actually
   * published. See F-D1-003.
   */
  it.fails("clears the marks the runtime discarded when the kernel died", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(event("explore.cell_state", { cell_id: "c2", state: "idle", marks: { c2: ["stale"] } }));
    expect(cell("c2").marks).toEqual(["stale"]);

    // Verbatim from `report_kernel_died`, which resets the marks server-side.
    apply(
      event("explore.kernel_state", { state: "dead", needs_restart: true }, "2026-09-05T10:01:00Z"),
    );

    expect(held().kernel.state).toBe("dead");
    expect(cell("c2").marks).toEqual(["never_run"]);
  });
});

/* -------------------------------------------------------------------------- */
/* §4.5 — "the slice applies events idempotently ... so order does not matter"  */
/* -------------------------------------------------------------------------- */

describe("order does not matter, for every event and not only three", () => {
  /**
   * Proves: two `changed_names` events for one cell do **not** converge on the
   * later one. `applyChangedNames` carries no watermark, so whichever frame the
   * socket happens to deliver last wins.
   *
   * Why the existing tests did not: "a late-arriving older event does not undo
   * a newer one" drives `cell_state` and `cell_output`, the two appliers that
   * compare `CellView.lastEventAt`. `changed_names` is asserted once, in order
   * ("changed_names writes the cell's changed set and the session's
   * unobservables"), so the applier with no guard at all is the one the
   * ordering suite never touches.
   *
   * The consequence is FR-022's, not a cosmetic one: `panelRefreshKey` reads
   * `CellView.changedNames`, so a reordered pair refreshes the panel bound to
   * the name the *older* run changed and leaves the panel bound to the name the
   * newer run actually changed showing a stale window.
   */
  it.fails("converges two changed_names events for one cell on the later one", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const first = event(
      "explore.changed_names",
      { cell_id: "c1", changed: ["alpha"], unobservable: [] },
      "2026-09-05T10:00:00Z",
    );
    const second = event(
      "explore.changed_names",
      { cell_id: "c1", changed: ["beta"], unobservable: [] },
      "2026-09-05T10:00:09Z",
    );

    apply(second);
    apply(first);

    expect(cell("c1").changedNames).toEqual(["beta"]);
    expect(panelRefreshKey(held(), "alpha")).toBe("");
  });

  /**
   * Proves: `changed_names` writes a session-wide field from a per-cell event,
   * so a second cell's event erases the unobservable names the first reported.
   *
   * Why the existing tests did not: the slice suite writes exactly one
   * `changed_names` event and reads `unobservableNames` back from it. Two cells
   * are never in play, so the session-scoped write from a cell-scoped event is
   * invisible.
   *
   * `unobservable` is the runtime's list of names it could not observe, and a
   * cell that changed nothing unobservable publishes `[]` — which is not a
   * statement that nothing anywhere is unobservable.
   */
  it.fails("keeps the unobservable names a different cell reported", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(
      event("explore.changed_names", { cell_id: "c1", changed: ["df"], unobservable: ["conn"] }),
    );
    expect(held().unobservableNames).toEqual(["conn"]);

    apply(
      event(
        "explore.changed_names",
        { cell_id: "c2", changed: ["head"], unobservable: [] },
        "2026-09-05T10:00:04Z",
      ),
    );

    expect(held().unobservableNames).toEqual(["conn"]);
  });

  /**
   * Proves: two `commit_recorded` events do not converge on the later commit.
   * `applyCommitRecorded` is last-write-wins with no timestamp comparison, so a
   * reordered pair leaves `notebookCommit` pointing at a superseded tree.
   *
   * Why the existing tests did not: "commit_recorded takes a branch commit as
   * the notebook's version" sends one event and checks the field. Ordering was
   * never in question for it.
   *
   * The consequence is FR-027's. `PauseControls` builds a packaged block's
   * decision as `{notebook_commit: session.notebookCommit}`, so an out-of-order
   * commit event makes Confirm send a commit the notebook is no longer at — and
   * that decision is what a later run replays.
   */
  it.fails("converges two commit_recorded events on the later commit", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const older = event(
      "explore.commit_recorded",
      { sha: "aaaaaaa", ref: "branch" },
      "2026-09-05T10:00:00Z",
    );
    const newer = event(
      "explore.commit_recorded",
      { sha: "bbbbbbb", ref: "branch" },
      "2026-09-05T10:00:30Z",
    );

    apply(newer);
    apply(older);

    expect(held().notebookCommit).toBe("bbbbbbb");
  });

  /**
   * Proves: a `session_opened` frame published before a `session_closed` reopens
   * a session the runtime has already closed.
   *
   * Why the existing tests did not: "session_closed closes the shell" and
   * "session_opened records what the session was opened over" are each a single
   * event on a fresh session. The pair is never delivered in the order the
   * socket can actually deliver it.
   */
  it.fails("does not reopen a closed session with an older session_opened", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const opened = event(
      "explore.session_opened",
      { notebook_path: PATH, opened_over: "block_outputs" },
      "2026-09-05T10:00:00Z",
    );
    apply(event("explore.session_closed", { notebook_path: PATH }, "2026-09-05T10:05:00Z"));
    expect(held().shellState).toBe("closed");

    apply(opened);

    expect(held().shellState).toBe("closed");
  });

  /**
   * Proves: an event for a session id that has been superseded writes into the
   * session that replaced it.
   *
   * `sessions` is keyed by notebook path and `sessionPathById` is only ever
   * added to — nothing but `forgetExploreSession` removes an id, and closing a
   * session does not call it. So when a notebook is closed and reopened, two
   * session ids point at one row, and a late frame from the dead session is
   * applied to the live one.
   *
   * Why the existing tests did not: every test in the slice suite uses one
   * session id, and "forgets a session and its id index together" removes the
   * row rather than replacing it. The two-ids-one-path state the reopen
   * actually produces is never constructed.
   *
   * The screen consequence is the FR-034 one: the toolbar reads
   * `kernelLabel(session)` and would show "needs restart" over a kernel that is
   * idle, because a session that is gone said so on its way out.
   */
  it.fails("ignores a kernel_state from the session id that a reopen replaced", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(
      event(
        "explore.kernel_state",
        { state: "idle", needs_restart: false },
        "2026-09-05T10:00:00Z",
      ),
    );
    apply(event("explore.session_closed", { notebook_path: PATH }, "2026-09-05T10:00:10Z"));

    // The person opens the same notebook again: a new session over one path.
    useAppStore
      .getState()
      .applyExploreSession(sessionResponse({ session_id: "sess-adv-2", has_kernel: true }));
    apply(
      event(
        "explore.kernel_state",
        { state: "idle", needs_restart: false },
        "2026-09-05T10:00:20Z",
        "sess-adv-2",
      ),
    );
    expect(held().kernel.state).toBe("idle");

    // The dead session's teardown frame, delayed on the wire.
    apply(
      event(
        "explore.kernel_state",
        { state: "dead", needs_restart: true },
        "2026-09-05T10:00:30Z",
        SESSION_ID,
      ),
    );

    expect(held().sessionId).toBe("sess-adv-2");
    expect(held().kernel.state).toBe("idle");
    expect(held().kernel.needsRestart).toBe(false);
  });

  /**
   * Proves: the §4.5 case by its own name — "a cell-state event may arrive
   * before the response to the command that caused it" — loses the event's
   * marks when the response lands.
   *
   * `applyExploreSession` rebuilds every cell through `cellFromModel`, which
   * takes `marks` from the response and keeps no held mark, and then resets
   * `lastMarksAt` to `null` so nothing can tell the two apart afterwards. A
   * session snapshot cut before the run therefore erases the run's marks.
   *
   * Why the existing tests did not: "an older marks map does not overwrite a
   * newer one" compares two *events*, which is the guarded path. The response
   * path is tested only against a fresh session ("writes the session from the
   * response and indexes it by session id", "is idempotent"), never against one
   * an event has already advanced.
   *
   * Left failing deliberately: the honest repair needs the session response to
   * carry the timestamp its snapshot was cut at, and `ExploreSessionResponse`
   * is `src/scistudio/**`. See F-D1-006.
   */
  it.fails("does not let an in-flight session response erase a newer event's marks", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(
      event(
        "explore.cell_state",
        { cell_id: "c1", state: "idle", marks: { c2: ["stale"] } },
        "2026-09-05T10:00:20Z",
      ),
    );
    expect(cell("c2").marks).toEqual(["stale"]);

    // The response to the open that was already in flight when the run ended:
    // a snapshot of the notebook as it was before, with no marks on it.
    useAppStore.getState().applyExploreSession(sessionResponse());

    expect(cell("c2").marks).toEqual(["stale"]);
  });

  /**
   * Proves: `cell_output` and `cell_state` share one watermark
   * (`CellView.lastEventAt`), so the one that loses the race is not merged —
   * it is dropped entirely, taking the fields the winner does not carry with
   * it. A cell whose output frame arrives after the `idle` frame that ended
   * its run shows **no output and no execution count**, for good.
   *
   * Why the existing tests did not: "a late-arriving older event does not undo
   * a newer one" is the test that established the watermark, and it delivers
   * two events of *the same* type carrying *the same* fields, which is the case
   * where dropping the older one is right. Two events of different types
   * carrying disjoint fields is the case where it is wrong, and nothing sends
   * that pair.
   *
   * This is the sharp edge of §4.5's claim. The slice's own module docstring
   * says "Two events for one cell therefore converge on the later one whichever
   * order they arrive in"; they do not converge, one is discarded.
   */
  it.fails("keeps a cell's output when its frame loses the race to the idle frame", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    apply(event("explore.cell_state", { cell_id: "c1", state: "running" }, "2026-09-05T10:00:01Z"));

    const output = event(
      "explore.cell_output",
      {
        cell_id: "c1",
        status: "ok",
        execution_count: 7,
        outputs: [{ output_type: "stream", name: "stdout", text: "loaded\n" }],
      },
      "2026-09-05T10:00:02Z",
    );
    const idle = event(
      "explore.cell_state",
      { cell_id: "c1", state: "idle", marks: {} },
      "2026-09-05T10:00:03Z",
    );

    apply(idle);
    apply(output);

    expect(cell("c1").runState).toBe("idle");
    expect(cell("c1").executionCount).toBe(7);
    expect(cell("c1").outputs).toHaveLength(1);
  });

  /**
   * Proves: forgetting a session leaves its buffered events behind, and any
   * later frame for that id starts filling the buffer again — up to
   * `PENDING_EVENT_CAP` entries that nothing will ever drain, because the id's
   * path is gone and only `session_opened` can name it again.
   *
   * Why the existing tests did not: "forgets a session and its id index
   * together" checks `sessions` and `sessionPathById` and does not look at
   * `pendingExploreEvents`; "buffers events for a session whose path is not
   * known yet, then drains them" only ever drains.
   *
   * Small on its own, and it is the mechanism behind the resurrection below.
   */
  it.fails("does not buffer events for a session the store was told to forget", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore.getState().forgetExploreSession(PATH);

    apply(event("explore.cell_state", { cell_id: "c1", state: "running" }));

    expect(useAppStore.getState().pendingExploreEvents[SESSION_ID] ?? []).toEqual([]);
    expect(useAppStore.getState().sessions[PATH]).toBeUndefined();
  });

  /**
   * Proves: order-independence holds across two sessions — a **negative
   * result**, recorded so the manager knows this ground is covered.
   *
   * Why the existing tests did not: every slice test uses one session id, so
   * "keyed by session id" is asserted by the module docstring and by nothing
   * else. Two sessions interleaved is the case a person actually creates by
   * having two Explore tabs open.
   */
  it("keeps two interleaved sessions apart, whatever the order", () => {
    const otherPath = "explore/second.ipynb";
    useAppStore.getState().applyExploreSession(sessionResponse());
    useAppStore
      .getState()
      .applyExploreSession(sessionResponse({ session_id: "sess-adv-b", notebook_path: otherPath }));

    apply(event("explore.cell_state", { cell_id: "c1", state: "running" }, "2026-09-05T10:00:03Z"));
    apply(
      event(
        "explore.cell_state",
        { cell_id: "c1", state: "idle", marks: { c1: ["stale"] } },
        "2026-09-05T10:00:02Z",
        "sess-adv-b",
      ),
    );
    apply(
      event(
        "explore.cell_output",
        { cell_id: "c1", status: "ok", execution_count: 4, outputs: [] },
        "2026-09-05T10:00:04Z",
      ),
    );

    expect(cell("c1").runState).toBe("running");
    expect(cell("c1").executionCount).toBe(4);
    expect(cell("c1").marks).toEqual([]);
    expect(cell("c1", otherPath).runState).toBe("idle");
    expect(cell("c1", otherPath).marks).toEqual(["stale"]);
    expect(cell("c1", otherPath).executionCount).toBeNull();
  });

  /**
   * Proves: applying the whole event set twice, in reverse, reaches the state
   * one forward pass reaches — the §4.5 claim stated in full rather than for
   * three appliers.
   *
   * Why the existing tests did not: "applying the same event twice is applying
   * it once" duplicates one `cell_state`. Nothing replays a stream.
   *
   * Kept in one test because a reader who wants to know whether the claim holds
   * wants one answer, not nine.
   */
  it.fails("reaches the same state from a stream replayed backwards", () => {
    const stream: ExploreSessionEventMessage[] = [
      event("explore.kernel_state", { state: "busy" }, "2026-09-05T10:00:01Z"),
      event("explore.cell_state", { cell_id: "c1", state: "running" }, "2026-09-05T10:00:02Z"),
      event(
        "explore.changed_names",
        { cell_id: "c1", changed: ["df"], unobservable: [] },
        "2026-09-05T10:00:03Z",
      ),
      event(
        "explore.cell_output",
        { cell_id: "c1", status: "ok", execution_count: 1, outputs: [] },
        "2026-09-05T10:00:04Z",
      ),
      event(
        "explore.cell_state",
        { cell_id: "c1", state: "idle", marks: { c2: ["stale"] } },
        "2026-09-05T10:00:05Z",
      ),
      event("explore.commit_recorded", { sha: "1111111", ref: "branch" }, "2026-09-05T10:00:06Z"),
      event("explore.kernel_state", { state: "idle" }, "2026-09-05T10:00:07Z"),
    ];

    useAppStore.getState().applyExploreSession(sessionResponse());
    for (const message of stream) apply(message);
    const forward = held();

    useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
    useAppStore.getState().applyExploreSession(sessionResponse());
    for (const message of [...stream].reverse()) apply(message);
    const backward = held();

    expect(backward.kernel.state).toBe(forward.kernel.state);
    expect(backward.notebookCommit).toBe(forward.notebookCommit);
    expect(backward.cells.map((each) => each.runState)).toEqual(
      forward.cells.map((each) => each.runState),
    );
    expect(backward.cells.map((each) => each.marks)).toEqual(
      forward.cells.map((each) => each.marks),
    );
    expect(backward.cells.map((each) => each.changedNames)).toEqual(
      forward.cells.map((each) => each.changedNames),
    );
    // The execution count is where the claim actually breaks: the backwards
    // pass drops the `cell_output` frame against the `idle` frame's watermark.
    expect(backward.cells.map((each) => each.executionCount)).toEqual(
      forward.cells.map((each) => each.executionCount),
    );
  });
});

/* -------------------------------------------------------------------------- */
/* FR-022 — the refresh boundary, from the other side                          */
/* -------------------------------------------------------------------------- */

describe("the refresh scoping refuses to fire for a name nothing changed (FR-022)", () => {
  /**
   * Proves: an empty changed set and a changed set naming something no panel is
   * bound to both leave every other panel's refresh key alone — a **negative
   * result**.
   *
   * Why the existing tests did not: `PanelSlots.test.tsx` proves the positive
   * ("re-reads only the panels bound to the names that changed") by mounting two
   * panels and changing one name. It never sends the two degenerate sets, and a
   * key built from a filtered list is exactly the kind of expression that goes
   * wrong when the filter matches nothing.
   */
  it("leaves an unbound panel's key alone for an empty and an unrelated set", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const before = panelRefreshKey(held(), "untouched");

    apply(event("explore.changed_names", { cell_id: "c1", changed: [], unobservable: [] }));
    expect(panelRefreshKey(held(), "untouched")).toBe(before);

    apply(
      event(
        "explore.changed_names",
        { cell_id: "c1", changed: ["something_else"], unobservable: [] },
        "2026-09-05T10:00:02Z",
      ),
    );
    expect(panelRefreshKey(held(), "untouched")).toBe(before);
    expect(panelRefreshKey(held(), "something_else")).not.toBe("");
  });

  /**
   * Proves: two panels bound to the same name both see the same refresh key, so
   * FR-022 refreshes both rather than one — a **negative result** for the
   * "two panels bound to the same name" boundary.
   *
   * Why the existing tests did not: `noteExplorePanelOpened` keys slots by
   * `boundName::panelId`, so two panels over one name is a state the slice
   * allows and no test constructs.
   */
  it("refreshes every panel bound to a changed name, not just the first", () => {
    useAppStore.getState().applyExploreSession(sessionResponse());
    const store = useAppStore.getState();
    store.noteExplorePanelOpened(SESSION_ID, {
      panelId: "df::panel.table",
      boundName: "df",
      pinned: false,
      frozen: false,
    });
    store.noteExplorePanelOpened(SESSION_ID, {
      panelId: "df::panel.chart",
      boundName: "df",
      pinned: false,
      frozen: false,
    });

    const before = panelRefreshKey(held(), "df");
    apply(event("explore.changed_names", { cell_id: "c1", changed: ["df"], unobservable: [] }));

    expect(held().panels).toHaveLength(2);
    expect(panelRefreshKey(held(), "df")).not.toBe(before);
    // One key for one name: both slots read it, so both re-issue their read.
    expect(held().panels.every((slot) => slot.boundName === "df")).toBe(true);
  });
});
