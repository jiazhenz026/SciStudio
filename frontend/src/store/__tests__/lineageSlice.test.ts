/**
 * lineageSlice tests — D38-2.4c IMPL.
 *
 * Mirrors the contract documented in ../lineageSlice.ts. Uses the global
 * ``useAppStore`` (not a fresh Zustand instance) so the slice integrates
 * with the rest of the app shape; we reset the lineage section before
 * each test to avoid cross-contamination.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { useAppStore } from "../index";
import type { LineageRunDetail, LineageRunSummary } from "../../types/lineage";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      lineage: {
        getRuns: vi.fn(),
        getRun: vi.fn(),
        getRunMethods: vi.fn(),
        validateRerun: vi.fn(),
        rerunRun: vi.fn(),
      },
    },
  };
});

import { api } from "../../lib/api";

const getRunsMock = vi.mocked(api.lineage.getRuns);
const getRunMock = vi.mocked(api.lineage.getRun);

function makeRun(overrides: Partial<LineageRunSummary> = {}): LineageRunSummary {
  return {
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
    block_count: 1,
    duration_ms: 5000,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<LineageRunDetail> = {}): LineageRunDetail {
  return {
    run: makeRun(),
    blocks: [],
    environment_snapshot: {},
    workflow_yaml_snapshot: null,
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

describe("lineageSlice", () => {
  beforeEach(() => {
    resetLineage();
    getRunsMock.mockReset();
    getRunMock.mockReset();
  });

  afterEach(() => {
    resetLineage();
  });

  it("starts with empty list state", () => {
    const s = useAppStore.getState();
    expect(s.runs).toEqual([]);
    expect(s.runsLoading).toBe(false);
    expect(s.runsError).toBe(null);
    expect(s.selectedRunId).toBe(null);
    expect(s.runDetails).toEqual({});
    expect(s.expandedBlockExecutionIds).toEqual([]);
  });

  it("fetchRuns success populates runs and clears loading", async () => {
    getRunsMock.mockResolvedValueOnce({
      runs: [makeRun({ run_id: "a" }), makeRun({ run_id: "b" })],
    });
    await useAppStore.getState().fetchRuns();
    const s = useAppStore.getState();
    expect(s.runs).toHaveLength(2);
    expect(s.runsLoading).toBe(false);
    expect(s.runsError).toBe(null);
  });

  it("fetchRuns failure preserves prior runs and sets error", async () => {
    getRunsMock.mockResolvedValueOnce({ runs: [makeRun({ run_id: "a" })] });
    await useAppStore.getState().fetchRuns();
    getRunsMock.mockRejectedValueOnce(new Error("network down"));
    await useAppStore.getState().fetchRuns();
    const s = useAppStore.getState();
    expect(s.runs).toHaveLength(1);
    expect(s.runsError).toContain("network down");
    expect(s.runsLoading).toBe(false);
  });

  it("fetchRunDetail writes to runDetails keyed by run_id", async () => {
    const detail = makeDetail();
    getRunMock.mockResolvedValueOnce(detail);
    await useAppStore.getState().fetchRunDetail("r1");
    const s = useAppStore.getState();
    expect(s.runDetails["r1"]).toEqual(detail);
    expect(s.runDetailLoading["r1"]).toBe(false);
    expect(s.runDetailError["r1"]).toBe(null);
  });

  it("fetchRunDetail maps 404 ApiError to 'Run not found'", async () => {
    getRunMock.mockRejectedValueOnce(new ApiError("missing", 404));
    await useAppStore.getState().fetchRunDetail("ghost");
    const s = useAppStore.getState();
    expect(s.runDetailError["ghost"]).toBe("Run not found");
    expect(s.runDetailLoading["ghost"]).toBe(false);
  });

  it("selectRun triggers fetchRunDetail on cache miss only", async () => {
    getRunMock.mockResolvedValue(makeDetail());
    useAppStore.getState().selectRun("r1");
    // Wait for the microtask kicked off by selectRun.
    await new Promise((r) => setTimeout(r, 0));
    expect(getRunMock).toHaveBeenCalledTimes(1);
    // Cache hit — no new fetch.
    useAppStore.getState().selectRun("r1");
    await new Promise((r) => setTimeout(r, 0));
    expect(getRunMock).toHaveBeenCalledTimes(1);
    // Null clears selection without fetching.
    useAppStore.getState().selectRun(null);
    await new Promise((r) => setTimeout(r, 0));
    expect(useAppStore.getState().selectedRunId).toBe(null);
    expect(getRunMock).toHaveBeenCalledTimes(1);
  });

  it("toggleBlockExecutionExpanded toggles set membership", () => {
    const s = useAppStore.getState();
    expect(s.expandedBlockExecutionIds).toEqual([]);
    s.toggleBlockExecutionExpanded("be-1");
    expect(useAppStore.getState().expandedBlockExecutionIds).toEqual(["be-1"]);
    s.toggleBlockExecutionExpanded("be-2");
    expect(useAppStore.getState().expandedBlockExecutionIds).toEqual(["be-1", "be-2"]);
    s.toggleBlockExecutionExpanded("be-1");
    expect(useAppStore.getState().expandedBlockExecutionIds).toEqual(["be-2"]);
  });

  it("openMethodsDialog sets id and fetches detail on cache miss", async () => {
    getRunMock.mockResolvedValueOnce(makeDetail());
    useAppStore.getState().openMethodsDialog("r1");
    expect(useAppStore.getState().methodsDialogRunId).toBe("r1");
    await new Promise((r) => setTimeout(r, 0));
    expect(getRunMock).toHaveBeenCalledWith("r1");
  });

  it("closeMethodsDialog clears the id", () => {
    useAppStore.setState({ methodsDialogRunId: "r1" });
    useAppStore.getState().closeMethodsDialog();
    expect(useAppStore.getState().methodsDialogRunId).toBe(null);
  });

  it("clearLineage resets every field", async () => {
    getRunsMock.mockResolvedValueOnce({ runs: [makeRun()] });
    await useAppStore.getState().fetchRuns();
    useAppStore.setState({
      selectedRunId: "r1",
      expandedBlockExecutionIds: ["be-1"],
      methodsDialogRunId: "r1",
      rerunDialogRunId: "r1",
      runDetails: { r1: makeDetail() },
      runDetailError: { r1: "x" },
      runDetailLoading: { r1: true },
    });
    useAppStore.getState().clearLineage();
    const s = useAppStore.getState();
    expect(s.runs).toEqual([]);
    expect(s.selectedRunId).toBe(null);
    expect(s.runDetails).toEqual({});
    expect(s.runDetailLoading).toEqual({});
    expect(s.runDetailError).toEqual({});
    expect(s.expandedBlockExecutionIds).toEqual([]);
    expect(s.methodsDialogRunId).toBe(null);
    expect(s.rerunDialogRunId).toBe(null);
  });
});
