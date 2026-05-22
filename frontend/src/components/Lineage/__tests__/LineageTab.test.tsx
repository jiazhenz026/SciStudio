/**
 * LineageTab.test.tsx — D38-2.4c IMPL tests.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        validateRerun: vi.fn().mockResolvedValue({ input_warnings: [], env_warnings: [] }),
        rerunRun: vi.fn().mockResolvedValue({ new_run_id: "" }),
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
    rerunDialogRunId: null,
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

  it("renders RerunDialog when rerunDialogRunId is set", () => {
    useAppStore.setState({ rerunDialogRunId: "abc-123" });
    render(<LineageTab />);
    expect(screen.getByTestId("rerun-dialog")).toBeInTheDocument();
  });
});
