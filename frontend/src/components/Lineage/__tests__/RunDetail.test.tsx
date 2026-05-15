/**
 * RunDetail.test.tsx — D38-2.4c IMPL tests (covers BlockExecutionCard too).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import type {
  LineageBlockExecution,
  LineageRunDetail,
  LineageRunSummary,
} from "../../../types/lineage";
import { RunDetail } from "../RunDetail";

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>(
    "../../../lib/api",
  );
  return {
    ...actual,
    api: {
      ...actual.api,
      lineage: {
        getRuns: vi.fn().mockResolvedValue({ runs: [] }),
        getRun: vi.fn(),
        getRunMethods: vi.fn(),
        validateRerun: vi.fn(),
        rerunRun: vi.fn(),
      },
    },
  };
});

function makeRun(
  overrides: Partial<LineageRunSummary> = {},
): LineageRunSummary {
  return {
    run_id: "r1",
    workflow_id: "image_pipeline",
    workflow_git_commit: null,
    workflow_dirty: false,
    started_at: "2026-05-15T14:30:00Z",
    finished_at: "2026-05-15T14:30:05Z",
    status: "completed",
    triggered_by: "user",
    parent_run_id: null,
    execute_from_block_id: null,
    block_count: 1,
    duration_ms: 5000,
    ...overrides,
  };
}

function makeBlock(
  overrides: Partial<LineageBlockExecution> = {},
): LineageBlockExecution {
  return {
    block_execution_id: "be-001",
    block_id: "load_image_1",
    block_type: "LoadImage",
    block_version: "0.1.0",
    block_config_resolved: { path: "/tmp/img.tif" },
    started_at: "2026-05-15T14:30:00Z",
    finished_at: "2026-05-15T14:30:03Z",
    duration_ms: 3000,
    termination: "completed",
    termination_detail: null,
    inputs: [],
    outputs: [],
    ...overrides,
  };
}

function makeDetail(
  overrides: Partial<LineageRunDetail> = {},
): LineageRunDetail {
  return {
    run: makeRun(),
    blocks: [makeBlock()],
    environment_snapshot: { scieasy: "0.1.0" },
    workflow_yaml_snapshot: "id: image_pipeline\nblocks: []\n",
    ...overrides,
  };
}

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

describe("RunDetail", () => {
  beforeEach(() => {
    resetLineage();
  });

  afterEach(() => {
    cleanup();
    resetLineage();
  });

  it("renders the empty state when no run selected", () => {
    render(<RunDetail />);
    expect(screen.getByTestId("run-detail-empty")).toBeInTheDocument();
  });

  it("renders the loading state while the detail is fetching", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetailLoading: { r1: true },
    });
    render(<RunDetail />);
    expect(screen.getByTestId("run-detail-loading")).toBeInTheDocument();
  });

  it("renders the error state when fetch failed", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetailError: { r1: "Not found" },
    });
    render(<RunDetail />);
    const err = screen.getByTestId("run-detail-error");
    expect(err.textContent).toContain("Not found");
  });

  it("renders the happy path with header + blocks list", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: { r1: makeDetail() },
    });
    render(<RunDetail />);
    expect(screen.getByTestId("run-detail")).toBeInTheDocument();
    expect(
      screen.getByTestId("block-execution-card-be-001"),
    ).toBeInTheDocument();
  });

  it("dispatches openRerunDialog when Re-run clicked", () => {
    const spy = vi.fn();
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: { r1: makeDetail() },
      openRerunDialog: spy,
    });
    render(<RunDetail />);
    fireEvent.click(screen.getByTestId("run-detail-rerun-button"));
    expect(spy).toHaveBeenCalledWith("r1");
  });

  it("dispatches openMethodsDialog when Export methods clicked", () => {
    const spy = vi.fn();
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: { r1: makeDetail() },
      openMethodsDialog: spy,
    });
    render(<RunDetail />);
    fireEvent.click(screen.getByTestId("run-detail-methods-button"));
    expect(spy).toHaveBeenCalledWith("r1");
  });

  it("disables Re-run button when run is still running", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({ status: "running", finished_at: null, duration_ms: null }),
        }),
      },
    });
    render(<RunDetail />);
    const btn = screen.getByTestId("run-detail-rerun-button");
    expect(btn.getAttribute("aria-disabled")).toBe("true");
  });

  it("renders the Parent run row when parent_run_id is set", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({ parent_run_id: "dead-beef-abcd-1234" }),
        }),
      },
    });
    render(<RunDetail />);
    expect(screen.getByText("Parent run")).toBeInTheDocument();
  });

  it("toggles a BlockExecutionCard body via the toggle button", () => {
    const spy = vi.fn();
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: { r1: makeDetail() },
      toggleBlockExecutionExpanded: spy,
    });
    render(<RunDetail />);
    fireEvent.click(
      screen.getByTestId("block-execution-card-toggle-be-001"),
    );
    expect(spy).toHaveBeenCalledWith("be-001");
  });

  it("makes parent_run_id clickable to navigate to the parent run", () => {
    const selectSpy = vi.fn();
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({ parent_run_id: "parent-run-abcd-1234" }),
        }),
      },
      selectRun: selectSpy,
    });
    render(<RunDetail />);
    const link = screen.getByTestId("run-detail-parent-link");
    expect(link.tagName).toBe("BUTTON");
    fireEvent.click(link);
    expect(selectSpy).toHaveBeenCalledWith("parent-run-abcd-1234");
  });

  it("renders the partial re-run banner when execute_from_block_id is set", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({
            execute_from_block_id: "threshold_1",
            parent_run_id: "parent-abc-1234-5678",
          }),
        }),
      },
    });
    render(<RunDetail />);
    const banner = screen.getByTestId("run-detail-partial-rerun-banner");
    expect(banner.textContent).toContain("Partial re-run");
    expect(banner.textContent).toContain("threshold_1");
    // The banner names the parent run id so the user can navigate back.
    expect(
      screen.getByTestId("run-detail-partial-rerun-parent-link"),
    ).toBeInTheDocument();
  });

  it("does NOT render the partial banner for a full run", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: { r1: makeDetail() },
    });
    render(<RunDetail />);
    expect(
      screen.queryByTestId("run-detail-partial-rerun-banner"),
    ).not.toBeInTheDocument();
  });

  it("renders the partial banner without a parent link when no parent_run_id", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({
            execute_from_block_id: "threshold_1",
            parent_run_id: null,
          }),
        }),
      },
    });
    render(<RunDetail />);
    const banner = screen.getByTestId("run-detail-partial-rerun-banner");
    expect(banner.textContent).toContain("Partial re-run");
    expect(
      screen.queryByTestId("run-detail-partial-rerun-parent-link"),
    ).not.toBeInTheDocument();
  });

  it("partial banner parent link dispatches selectRun(parent_run_id)", () => {
    const selectSpy = vi.fn();
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          run: makeRun({
            execute_from_block_id: "threshold_1",
            parent_run_id: "parent-xyz-9999",
          }),
        }),
      },
      selectRun: selectSpy,
    });
    render(<RunDetail />);
    fireEvent.click(
      screen.getByTestId("run-detail-partial-rerun-parent-link"),
    );
    expect(selectSpy).toHaveBeenCalledWith("parent-xyz-9999");
  });

  it("renders block error section when termination is 'error' and card expanded", () => {
    useAppStore.setState({
      selectedRunId: "r1",
      runDetails: {
        r1: makeDetail({
          blocks: [
            makeBlock({
              block_execution_id: "be-err",
              termination: "error",
              termination_detail: "boom",
            }),
          ],
        }),
      },
      expandedBlockExecutionIds: ["be-err"],
    });
    render(<RunDetail />);
    const errSection = screen.getByTestId("block-card-error");
    expect(errSection.textContent).toContain("boom");
  });
});
