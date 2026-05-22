/**
 * RerunDialog.test.tsx — D38-2.4c IMPL.
 *
 * Targeted coverage for Codex P1 (PR #944): rerun success must be treated
 * INDEPENDENTLY from list refresh. If `fetchRuns` fails after a successful
 * `rerunRun`, the dialog must still close so the user does not click
 * Re-run again and unintentionally launch a duplicate run.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { RerunDialog } from "../RerunDialog";

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>("../../../lib/api");
  const stubDetail = {
    run: {
      run_id: "r1",
      workflow_id: "wf",
      workflow_git_commit: null,
      workflow_dirty: false,
      started_at: "2026-05-15T14:30:00Z",
      finished_at: "2026-05-15T14:30:05Z",
      status: "completed" as const,
      triggered_by: "user" as const,
      parent_run_id: null,
      execute_from_block_id: null,
      block_count: 0,
      duration_ms: 5000,
    },
    blocks: [],
    environment_snapshot: {},
    workflow_yaml_snapshot: null,
  };
  return {
    ...actual,
    api: {
      ...actual.api,
      lineage: {
        getRuns: vi.fn().mockResolvedValue({ runs: [] }),
        getRun: vi.fn().mockResolvedValue(stubDetail),
        getRunMethods: vi.fn(),
        validateRerun: vi.fn().mockResolvedValue({ input_warnings: [], env_warnings: [] }),
        rerunRun: vi.fn().mockResolvedValue({ new_run_id: "" }),
      },
    },
  };
});

import { api } from "../../../lib/api";

const rerunRunMock = vi.mocked(api.lineage.rerunRun);
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

describe("RerunDialog", () => {
  beforeEach(() => {
    resetLineage();
    rerunRunMock.mockReset();
    getRunsMock.mockReset();
    rerunRunMock.mockResolvedValue({ new_run_id: "" });
    getRunsMock.mockResolvedValue({ runs: [] });
  });

  afterEach(() => {
    cleanup();
    resetLineage();
  });

  it("closes the dialog after rerun even if list refresh throws (Codex P1)", async () => {
    // Pre-populate detail so the dialog doesn't fall into a fetch loop.
    useAppStore.setState({
      runDetails: {
        r1: {
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
        },
      },
    });
    rerunRunMock.mockResolvedValueOnce({ new_run_id: "" });
    getRunsMock.mockRejectedValueOnce(new Error("transient refresh failure"));
    const onClose = vi.fn();
    render(<RerunDialog runId="r1" onClose={onClose} />);
    // Wait for validation to settle so the confirm button enables.
    const confirm = await screen.findByTestId("rerun-dialog-confirm");
    await waitFor(() => expect(confirm).not.toBeDisabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(rerunRunMock).toHaveBeenCalledWith("r1"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    // The rerun side effect went through; list refresh failure must not
    // surface as a "rerun failed" submit error on the dialog.
    expect(screen.queryByTestId("rerun-dialog-submit-error")).not.toBeInTheDocument();
  });

  it("surfaces rerun failure (not refresh failure) and keeps the dialog open", async () => {
    useAppStore.setState({
      runDetails: {
        r1: {
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
        },
      },
    });
    rerunRunMock.mockRejectedValueOnce(new Error("backend exploded"));
    const onClose = vi.fn();
    render(<RerunDialog runId="r1" onClose={onClose} />);
    const confirm = await screen.findByTestId("rerun-dialog-confirm");
    await waitFor(() => expect(confirm).not.toBeDisabled());
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(screen.getByTestId("rerun-dialog-submit-error")).toBeInTheDocument(),
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
