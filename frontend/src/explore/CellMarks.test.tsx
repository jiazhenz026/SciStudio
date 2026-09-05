/**
 * ADR-054 spec 4 (T-006) — the marks (FR-012, FR-013, FR-034; SC-004).
 *
 * The marks are driven here from the runtime's own events and responses rather
 * than from hand-built props, because the requirement is not "these badges
 * render" — it is that **what renders is what the runtime said**. So the store
 * is fed a `cell_state` event and a `MarksResponse`, and the component is
 * rendered from what the slice then holds.
 *
 * The last test is the negative one FR-034 asks for: a notebook whose written
 * order plainly implies a stale cell, with no mark on it, renders no mark. If
 * anything in the frontend ever starts computing marks, that test is the one
 * that goes red.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import type { CellView } from "../store/types";
import type { ExploreSessionResponse } from "../types/api";

import { CellMarks } from "./CellMarks";

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-marks";

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
      { cell_id: "c3", cell_type: "code", source: "df = other()", enabled: true, marks: [] },
    ],
  };
}

/** The cell as the slice holds it after the events under test. */
function held(cellId: string): CellView {
  const cell = useAppStore.getState().sessions[PATH].cells.find((row) => row.cellId === cellId);
  if (!cell) throw new Error(`no cell ${cellId}`);
  return cell;
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
  act(() => useAppStore.getState().applyExploreSession(sessionResponse()));
});

afterEach(cleanup);

describe("the marks the runtime reports (FR-012)", () => {
  it("draws never-run, stale and out-of-order from a cell-state event", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: {
          cell_id: "c2",
          state: "idle",
          marks: { c2: ["stale", "out_of_order"], c3: ["never_run"] },
        },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );

    render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    expect(screen.getByTestId("explore-cell-mark-stale-c2")).toBeTruthy();
    expect(screen.getByTestId("explore-cell-mark-out_of_order-c2")).toBeTruthy();
    expect(screen.queryByTestId("explore-cell-mark-never_run-c2")).toBeNull();
    cleanup();

    render(<CellMarks cell={held("c3")} onRunWithUpstream={vi.fn()} />);
    expect(screen.getByTestId("explore-cell-mark-never_run-c3")).toBeTruthy();
  });

  it("clears a mark the runtime no longer reports", () => {
    const apply = (marks: Record<string, string[]>, at: string) =>
      act(() =>
        useAppStore.getState().applyExploreSessionEvent({
          type: "explore.cell_state",
          session_id: SESSION_ID,
          data: { cell_id: "c2", state: "idle", marks },
          timestamp: at,
        }),
      );
    apply({ c2: ["stale"] }, "2026-09-05T12:00:00Z");
    apply({}, "2026-09-05T12:00:01Z");
    const { container } = render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("names the reads and the cells behind an out-of-order mark", () => {
    act(() =>
      useAppStore.getState().applyExploreMarks(SESSION_ID, {
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
      }),
    );
    render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    const reason = screen.getByTestId("explore-out-of-order-reason-c2").textContent ?? "";
    expect(reason).toContain("df");
    expect(reason).toContain("c3");
  });

  it("says so when the runtime marked the cell but named no reads", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c2: ["out_of_order"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    expect(screen.getByTestId("explore-out-of-order-reason-c2").textContent).toContain(
      "named no reads",
    );
  });
});

describe("the run-with-upstream control (FR-013)", () => {
  it("is offered on an out-of-order cell and sends that cell's id once", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c2: ["out_of_order"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    const onRunWithUpstream = vi.fn();
    render(<CellMarks cell={held("c2")} onRunWithUpstream={onRunWithUpstream} />);
    fireEvent.click(screen.getByTestId("explore-run-with-upstream-c2"));
    expect(onRunWithUpstream).toHaveBeenCalledTimes(1);
    expect(onRunWithUpstream).toHaveBeenCalledWith("c2");
  });

  it("is not offered on a stale cell, which has its own control on the toolbar", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c2: ["stale"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    expect(screen.queryByTestId("explore-run-with-upstream-c2")).toBeNull();
  });

  it("refuses to send while there is no session", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c2: ["out_of_order"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    const onRunWithUpstream = vi.fn();
    render(<CellMarks cell={held("c2")} disabled onRunWithUpstream={onRunWithUpstream} />);
    fireEvent.click(screen.getByTestId("explore-run-with-upstream-c2"));
    expect(onRunWithUpstream).not.toHaveBeenCalled();
  });
});

describe("no mark is derived here (FR-034)", () => {
  it("renders nothing for a cell the runtime has not marked, however it looks", () => {
    // c2 reads `df`, and c3 below it rebinds `df`: written order alone says
    // "out of order". The runtime has said nothing, so neither does the shell.
    const cell = held("c2");
    expect(cell.marks).toEqual([]);
    const { container } = render(<CellMarks cell={cell} onRunWithUpstream={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("ignores a value that is not one of the runtime's three marks", () => {
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c2: ["questionable", "stale"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    render(<CellMarks cell={held("c2")} onRunWithUpstream={vi.fn()} />);
    expect(screen.getByTestId("explore-cell-marks-c2").dataset.marks).toBe("stale");
  });
});
