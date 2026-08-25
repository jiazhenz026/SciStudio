/*
 * A tutorial step that writes the graph must leave it in front of the reader.
 *
 * The canvas keeps its own pan and zoom. A step writes a workflow file, the
 * nodes land where the file puts them, and a reader who had dragged the view
 * somewhere earlier is looking at empty space — while the step's next line
 * asks them to press Run on a graph that is not on screen. `fitView` as a
 * ReactFlow prop only runs on mount, so the frame has to be asked for.
 *
 * It is asked for on exactly one signal: a `workflow.changed` naming its
 * author. The reader's own edits must never move the viewport under them.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dispatchWorkflowEvent } from "../useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { useAppStore } from "../../store";

const DEPS = {
  appendLog: vi.fn(),
  setInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

function workflowChanged(changedBy: string | null): WorkflowEventMessage {
  return {
    type: "workflow.changed",
    workflow_id: "main",
    timestamp: "2026-08-25T00:00:00Z",
    data: {
      workflow_id: "main",
      entity_class: "workflow",
      entity_id: "main",
      version: 7,
      source: "external",
      source_id: null,
      kind: "modified",
      ...(changedBy === null ? {} : { changed_by: changedBy }),
    },
  } as WorkflowEventMessage;
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ workflowId: "main" });
});

describe("framing the canvas after a tutorial writes it", () => {
  it("asks for a fit when a tutorial step wrote the open workflow", () => {
    const before = useAppStore.getState().canvasFitRequestCounter;

    dispatchWorkflowEvent(workflowChanged("tutorial"), DEPS);

    expect(useAppStore.getState().canvasFitRequestCounter).toBe(before + 1);
  });

  it("leaves the viewport alone for a write nobody claimed", () => {
    // The watcher's echo of the app's own save, and the reader's own edits,
    // both arrive without an author. Fitting on those would yank the view out
    // from under someone mid-drag.
    const before = useAppStore.getState().canvasFitRequestCounter;

    dispatchWorkflowEvent(workflowChanged(null), DEPS);

    expect(useAppStore.getState().canvasFitRequestCounter).toBe(before);
  });

  it("leaves the viewport alone for a write to a workflow that is not open", () => {
    useAppStore.setState({ workflowId: "other" });
    const before = useAppStore.getState().canvasFitRequestCounter;

    dispatchWorkflowEvent(workflowChanged("tutorial"), DEPS);

    expect(useAppStore.getState().canvasFitRequestCounter).toBe(before);
  });
});
