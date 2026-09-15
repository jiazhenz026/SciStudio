/**
 * LineageTab.test.tsx — D38-2.4c IMPL tests.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { LineageTab } from "../LineageTab";
import type * as ApiModule from "../../../lib/api";

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      lineage: {
        getRuns: vi.fn().mockResolvedValue({ runs: [] }),
        getRun: vi.fn().mockResolvedValue({
          run: {
            run_id: "r1",
            workflow_id: "wf",
            workflow_git_commit: null,
            workflow_dirty: false,
            started_at: "2026-05-15T14:30:00Z",
            finished_at: "2026-05-15T14:30:05Z",
            status: "completed",
            triggered_by: "user",
            parent_run_id: null,
            execute_from_block_id: null,
            block_count: 0,
            duration_ms: 5000,
          },
          blocks: [],
          environment_snapshot: {},
          workflow_yaml_snapshot: null,
        }),
        getRunMethods: vi.fn().mockResolvedValue({ markdown: "# methods" }),
      },
    },
  };
});

import { api } from "../../../lib/api";

const getRunsMock = vi.mocked(api.lineage.getRuns);

function resetLineage(): void {
  useAppStore.setState({
    runs: [],
    runsLoading: false,
    runsError: null,
    selectedRunId: null,
    runDetails: {},
    runDetailLoading: {},
    runDetailError: {},
    expandedBlockExecutionIds: [],
    methodsDialogRunId: null,
  });
}

describe("LineageTab", () => {
  beforeEach(() => {
    resetLineage();
    getRunsMock.mockClear();
    getRunsMock.mockResolvedValue({ runs: [] });
  });

  afterEach(() => {
    cleanup();
    resetLineage();
  });

  it("refreshes when any workflow finishes, not when the projected flag flips (#2395)", async () => {
    useAppStore.getState().resetExecution();
    useAppStore.setState({ workflowId: "main", tabs: [], activeTabId: null });
    render(<LineageTab />);
    await waitFor(() => expect(getRunsMock).toHaveBeenCalledTimes(1));

    const lifecycle = (type: string, workflowId: string) =>
      useAppStore
        .getState()
        .consumeEvent({ type, block_id: null, workflow_id: workflowId, data: {}, timestamp: "" });

    // A workflow that is not on screen finishing still refreshes the list.
    act(() => lifecycle("workflow_started", "long_wf"));
    act(() => lifecycle("workflow_started", "short_wf"));
    act(() => lifecycle("workflow_completed", "short_wf"));
    await waitFor(() => expect(getRunsMock).toHaveBeenCalledTimes(2));

    // Changing which workflow is on screen alone does not refetch.
    act(() => useAppStore.setState({ isRunning: true }));
    act(() => useAppStore.setState({ isRunning: false }));
    expect(getRunsMock).toHaveBeenCalledTimes(2);

    act(() => lifecycle("workflow_completed", "long_wf"));
    await waitFor(() => expect(getRunsMock).toHaveBeenCalledTimes(3));
    useAppStore.getState().resetExecution();
  });

  it("renders the two-pane layout", () => {
    render(<LineageTab />);
    expect(screen.getByTestId("lineage-tab")).toBeInTheDocument();
    expect(screen.getByTestId("lineage-tab-list-pane")).toBeInTheDocument();
    expect(screen.getByTestId("lineage-tab-detail-pane")).toBeInTheDocument();
  });

  it("fires fetchRuns on mount", () => {
    render(<LineageTab />);
    expect(getRunsMock).toHaveBeenCalled();
  });

  it("renders the empty state when no runs and not loading", async () => {
    render(<LineageTab />);
    await waitFor(() => expect(screen.getByTestId("lineage-tab-empty")).toBeInTheDocument());
  });

  it("renders an error banner with Retry that calls fetchRuns again", async () => {
    getRunsMock.mockRejectedValueOnce(new Error("Network down"));
    render(<LineageTab />);
    const banner = await screen.findByTestId("lineage-tab-error");
    expect(banner).toHaveTextContent("Could not load runs: Network down");
    const callsBefore = getRunsMock.mock.calls.length;
    fireEvent.click(screen.getByTestId("lineage-tab-error-retry"));
    expect(getRunsMock.mock.calls.length).toBe(callsBefore + 1);
  });

  it("renders MethodsExportDialog when methodsDialogRunId is set", () => {
    useAppStore.setState({ methodsDialogRunId: "abc-123" });
    render(<LineageTab />);
    expect(screen.getByTestId("methods-export-dialog")).toBeInTheDocument();
  });

  // ADR-038 Addendum 1 §11.4 (#2033): Re-run is withdrawn. The `r` key used
  // to open its dialog even though the button had been removed in #1721 —
  // a decommissioned feature still reachable by keystroke.
  it("does not open any dialog when 'r' is pressed with a run selected", () => {
    useAppStore.setState({ selectedRunId: "abc-123" });
    render(<LineageTab />);
    fireEvent.keyDown(window, { key: "r" });
    expect(screen.queryByTestId("rerun-dialog")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-dialog")).not.toBeInTheDocument();
  });
});
