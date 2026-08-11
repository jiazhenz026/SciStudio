/**
 * ADR-053 Learning Center (#2057) — steps advance on screen, not just on disk.
 *
 * Spec §2 User Story 1, acceptance 3: when the user drags a Load block onto the
 * canvas, the step is satisfied *without any further user action* and the next
 * step is displayed. The backend judged and persisted that correctly on its
 * own, but nothing told the frontend, so a reader kept looking at a step they
 * had already finished. These tests cover the half that was missing.
 *
 * No new WebSocket frame is involved. The events asserted here are already in
 * `_OUTBOUND_EVENTS` and already reach this client; the frontend reacts to
 * "something changed" and the backend remains the sole judge.
 */

import { cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LearningCenterModule from "../../lib/api/learningCenter";
import { learningCenterApi, type TutorialSessionResponse } from "../../lib/api/learningCenter";
import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { useBottomPanelControls } from "../../App.parts/useBottomPanelControls";
import { useAppStore } from "../../store";
import { TUTORIAL_SYNC_EVENT_TYPES } from "../../store/learningCenterSlice";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { ActiveStep } from "../LearningCenter.parts/ActiveStep";

vi.mock("../../lib/api/learningCenter", async (importOriginal) => {
  const actual = await importOriginal<typeof LearningCenterModule>();
  return {
    ...actual,
    learningCenterApi: {
      getTutorialCatalogue: vi.fn(),
      getActiveTutorialSession: vi.fn(),
      startTutorialSession: vi.fn(),
      evaluateActiveTutorialStep: vi.fn(),
      reportTutorialUiEvent: vi.fn(),
      continueActiveTutorialStep: vi.fn(),
      leaveActiveTutorialSession: vi.fn(),
      getTutorialProgress: vi.fn(),
      previewTutorialDataClear: vi.fn(),
      clearTutorialData: vi.fn(),
      getTutorialUnlock: vi.fn(),
      dismissTutorialUnlock: vi.fn(),
    },
  };
});

function session(stepId: string, say: string, index = 0): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "welcome-to-scistudio",
    title: "Welcome to SciStudio",
    project_id: "p1",
    project_path: "/Users/rosalind/SciStudio Tutorials/welcome",
    step: {
      id: stepId,
      index,
      total: 4,
      title: null,
      say,
      highlight: null,
      route_to: null,
      prefill: [],
      awaiting_continue: false,
      satisfied: false,
    },
    satisfied_step_ids: [],
    status: "active",
    error: null,
    replay: null,
  };
}

function engineEvent(type: string): WorkflowEventMessage {
  return { type, data: {}, timestamp: "2026-01-01T00:00:00Z" };
}

const deps = {
  appendLog: vi.fn(),
  setInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  resetAppStore();
  /*
   * `openBlockSourceTab` fetches the source and alerts on failure. Neither is
   * what these tests are about, but an unstubbed fetch would make the tab open
   * fail and put a jsdom "not implemented: window.alert" through every run.
   */
  vi.stubGlobal("alert", vi.fn());
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ source: "# block source", path: "/blocks/load_data.py" }),
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a step advances when an engine event says something changed", () => {
  it("re-asks the backend and renders the step that comes back", async () => {
    useAppStore.setState({
      learningCenterSession: session("drag-load", "Drag a Load block onto the canvas."),
    });
    render(<ActiveStep />);
    expect(screen.getByText("Drag a Load block onto the canvas.")).toBeInTheDocument();

    vi.mocked(learningCenterApi.evaluateActiveTutorialStep).mockResolvedValue(
      session("point-load-at-the-data", "Now point the Load block at the CSV.", 1),
    );

    // The event the product already sends when a node lands on the canvas.
    dispatchWorkflowEvent(engineEvent("workflow.changed"), deps);

    expect(await screen.findByText("Now point the Load block at the CSV.")).toBeInTheDocument();
    // No click, no confirmation — the step that was showing is gone.
    expect(screen.queryByText("Drag a Load block onto the canvas.")).not.toBeInTheDocument();
    expect(screen.getByText("Step 2 of 4")).toBeInTheDocument();
  });

  it("asks nothing at all when no tutorial is running", async () => {
    render(<ActiveStep />);

    for (const type of TUTORIAL_SYNC_EVENT_TYPES) {
      dispatchWorkflowEvent(engineEvent(type), deps);
    }

    await Promise.resolve();
    expect(learningCenterApi.evaluateActiveTutorialStep).not.toHaveBeenCalled();
    expect(learningCenterApi.getActiveTutorialSession).not.toHaveBeenCalled();
  });

  it("ignores events that cannot change whether a step is done", async () => {
    useAppStore.setState({ learningCenterSession: session("drag-load", "Drag a Load block.") });

    dispatchWorkflowEvent(engineEvent("block_running"), deps);
    dispatchWorkflowEvent(engineEvent("workflow_started"), deps);

    await Promise.resolve();
    expect(learningCenterApi.evaluateActiveTutorialStep).not.toHaveBeenCalled();
  });

  it("covers FR-050's table, minus the event that never arrives inbound", () => {
    expect([...TUTORIAL_SYNC_EVENT_TYPES].sort()).toEqual(
      [
        "block_done",
        "block_error",
        "blocks.reloaded",
        "file.changed",
        "git.head_changed",
        "workflow.changed",
        "workflow_completed",
      ].sort(),
    );
    // `interactive_complete` travels frontend to backend and is not in
    // `_OUTBOUND_EVENTS`, so there is no inbound event to react to.
    expect(TUTORIAL_SYNC_EVENT_TYPES.has("interactive_complete")).toBe(false);
  });

  it("uses evaluate, which also covers the conditions no event reaches", async () => {
    useAppStore.setState({ learningCenterSession: session("make-tiff", "Write the TIFF.") });
    vi.mocked(learningCenterApi.evaluateActiveTutorialStep).mockResolvedValue(
      session("make-tiff", "Write the TIFF."),
    );

    dispatchWorkflowEvent(engineEvent("block_done"), deps);

    // `file.changed` is filtered to an extension allowlist, so a `file_exists`
    // condition on a TIFF is never event-driven (FR-053). Asking with evaluate
    // rather than a plain read covers it at the same cost.
    await waitFor(() =>
      expect(learningCenterApi.evaluateActiveTutorialStep).toHaveBeenCalledTimes(1),
    );
  });

  it("drops the session view when the backend says it is gone", async () => {
    const { ApiError } = await import("../../lib/api/core");
    useAppStore.setState({ learningCenterSession: session("drag-load", "Drag a Load block.") });
    vi.mocked(learningCenterApi.evaluateActiveTutorialStep).mockRejectedValue(
      new ApiError("No tutorial is running.", 404),
    );

    dispatchWorkflowEvent(engineEvent("block_done"), deps);

    await waitFor(() => expect(useAppStore.getState().learningCenterSession).toBeNull());
    // A session that ended is an answer, not an error to put in front of anyone.
    expect(useAppStore.getState().learningCenterError).toBeNull();
  });
});

describe("a burst of events does not become a burst of requests", () => {
  it("coalesces to one in-flight request plus one trailing catch-up", async () => {
    useAppStore.setState({ learningCenterSession: session("drag-load", "Drag a Load block.") });

    let release: (value: TutorialSessionResponse) => void = () => {};
    const pending = new Promise<TutorialSessionResponse>((resolve) => {
      release = resolve;
    });
    vi.mocked(learningCenterApi.evaluateActiveTutorialStep)
      .mockReturnValueOnce(pending)
      .mockResolvedValue(session("settled", "Settled.", 1));

    // Six events, as a drag would produce.
    for (let i = 0; i < 6; i += 1) {
      dispatchWorkflowEvent(engineEvent("workflow.changed"), deps);
    }

    // Only the first has gone out; the other five collapsed into one flag.
    expect(learningCenterApi.evaluateActiveTutorialStep).toHaveBeenCalledTimes(1);

    release(session("drag-load", "Drag a Load block."));

    // Exactly one trailing request follows, so the last event in the burst is
    // still answered — that is the one that usually completes the step.
    await waitFor(() =>
      expect(learningCenterApi.evaluateActiveTutorialStep).toHaveBeenCalledTimes(2),
    );
    expect(learningCenterApi.evaluateActiveTutorialStep).toHaveBeenCalledTimes(2);
  });
});

describe("interface events the backend cannot observe (FR-052)", () => {
  it("reports preview_expanded when the preview is enlarged", async () => {
    useAppStore.setState({ learningCenterSession: session("look", "Enlarge the preview.") });
    vi.mocked(learningCenterApi.reportTutorialUiEvent).mockResolvedValue(
      session("look", "Enlarge the preview."),
    );

    await useAppStore.getState().reportTutorialUiEvent("preview_expanded");

    expect(learningCenterApi.reportTutorialUiEvent).toHaveBeenCalledWith("preview_expanded");
  });

  it("reports block_source_viewed when a block's source is opened", async () => {
    useAppStore.setState({ learningCenterSession: session("read", "Open the block source.") });
    vi.mocked(learningCenterApi.reportTutorialUiEvent).mockResolvedValue(
      session("read", "Open the block source."),
    );

    useAppStore.getState().openBlockSourceTab("load_data");

    await waitFor(() =>
      expect(learningCenterApi.reportTutorialUiEvent).toHaveBeenCalledWith("block_source_viewed"),
    );
  });

  it("reports node_selected when the reader clicks a node on the canvas", async () => {
    // The step "click the block to view its output" waits on this: the backend
    // is told which workflow is open and never which node is selected, so the
    // frontend is the only place the fact exists (FR-052).
    useAppStore.setState({ learningCenterSession: session("look", "Click the block.") });
    vi.mocked(learningCenterApi.reportTutorialUiEvent).mockResolvedValue(
      session("look", "Click the block."),
    );

    const { result } = renderHook(() =>
      useBottomPanelControls({
        bottomPanelPinned: false,
        setSelectedNodeId: vi.fn(),
        setActiveBottomTab: vi.fn(),
      }),
    );
    result.current.handleNodeSelect("node-1");

    await waitFor(() =>
      expect(learningCenterApi.reportTutorialUiEvent).toHaveBeenCalledWith("node_selected"),
    );
  });

  it("reports nothing when no tutorial is running", async () => {
    await useAppStore.getState().reportTutorialUiEvent("preview_expanded");
    useAppStore.getState().openBlockSourceTab("load_data");

    await Promise.resolve();
    expect(learningCenterApi.reportTutorialUiEvent).not.toHaveBeenCalled();
  });
});
