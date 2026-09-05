/**
 * ADR-054 spec 4 (T-001) — every session event routes to the slice (FR-033).
 *
 * The dispatcher's job here is narrow and worth pinning: the frames arrive on
 * the WebSocket the workflow already uses, so an `explore.*` frame must reach
 * the slice, must be reported as consumed so it does not also land in the
 * execution log as an unknown type, and must not disturb the engine branches
 * that share the socket.
 *
 * Routing is by prefix rather than by a list of names, which is what makes a
 * new session event type reach the slice without a second edit in
 * `dispatchEvent.ts` — that is asserted directly below.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import { EXPLORE_EVENT_TYPES } from "../../types/api";
import type { WorkflowEventMessage } from "../../types/api";
import { useAppStore } from "../index";

const SESSION_ID = "sess-route";
const PATH = "explore/route.ipynb";

const DEPS = {
  appendLog: vi.fn(),
  setInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

function frame(type: string, data: Record<string, unknown> = {}): WorkflowEventMessage {
  return {
    type,
    session_id: SESSION_ID,
    data,
    timestamp: "2026-09-05T11:00:00Z",
  } as unknown as WorkflowEventMessage;
}

function openSession() {
  useAppStore.getState().applyExploreSession({
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: false,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [{ cell_id: "c1", cell_type: "code", source: "x = 1", enabled: true, marks: [] }],
  });
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
  DEPS.appendLog.mockReset();
  DEPS.setInteractivePrompt.mockReset();
  DEPS.setWorkflow.mockReset();
});

describe("dispatchWorkflowEvent routes the session events (FR-033)", () => {
  it("consumes every one of the nine event types", () => {
    for (const type of EXPLORE_EVENT_TYPES) {
      expect(dispatchWorkflowEvent(frame(type), DEPS), `${type} must be consumed`).toBe(true);
    }
  });

  it("routes by prefix, so an event type added later still reaches the slice", () => {
    // Not a real event — the point is that the dispatcher does not gate on a
    // hard-coded list, so spec 3 can publish a new session event and the
    // frontend routes it without a change here.
    expect(dispatchWorkflowEvent(frame("explore.some_future_event"), DEPS)).toBe(true);
  });

  it("actually changes the slice rather than only claiming the frame", () => {
    openSession();
    dispatchWorkflowEvent(
      frame("explore.kernel_state", { state: "busy", needs_restart: false }),
      DEPS,
    );
    expect(useAppStore.getState().sessions[PATH].kernel.state).toBe("busy");

    dispatchWorkflowEvent(frame("explore.cell_state", { cell_id: "c1", state: "running" }), DEPS);
    expect(useAppStore.getState().sessions[PATH].cells[0].runState).toBe("running");
  });

  it("buffers a session event that arrives before its path is known", () => {
    dispatchWorkflowEvent(frame("explore.cell_state", { cell_id: "c1", state: "running" }), DEPS);
    expect(useAppStore.getState().pendingExploreEvents[SESSION_ID]).toHaveLength(1);
    openSession();
    expect(useAppStore.getState().sessions[PATH].cells[0].runState).toBe("running");
  });

  it("writes nothing to the execution log for a session event", () => {
    openSession();
    for (const type of EXPLORE_EVENT_TYPES) {
      dispatchWorkflowEvent(frame(type, { notebook_path: PATH }), DEPS);
    }
    expect(DEPS.appendLog).not.toHaveBeenCalled();
  });

  it("leaves the engine's own frames alone", () => {
    // A workflow event is not consumed here; it falls through to `consumeEvent`
    // exactly as it did before the Explore branch was added.
    const engine: WorkflowEventMessage = {
      type: "block_done",
      data: {},
      timestamp: "2026-09-05T11:00:00Z",
    };
    expect(dispatchWorkflowEvent(engine, DEPS)).toBe(false);
    // And a type that merely *contains* "explore" is not one of ours: the
    // prefix is anchored at the start.
    const notOurs: WorkflowEventMessage = {
      type: "block_explore_finished",
      data: {},
      timestamp: "2026-09-05T11:00:00Z",
    };
    expect(dispatchWorkflowEvent(notOurs, DEPS)).toBe(false);
  });
});
