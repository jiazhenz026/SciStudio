/**
 * RunsList.test.tsx — D38-2.4c IMPL tests.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import type { LineageRunSummary } from "../../../types/lineage";
import { RunsList } from "../RunsList";

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
    run_id: "00000000-0000-0000-0000-000000000001",
    workflow_id: "image_pipeline",
    workflow_git_commit: "abc1234567",
    workflow_dirty: false,
    started_at: "2026-05-15T14:30:00Z",
    finished_at: "2026-05-15T14:30:12Z",
    status: "completed",
    triggered_by: "user",
    parent_run_id: null,
    execute_from_block_id: null,
    block_count: 4,
    duration_ms: 12000,
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

describe("RunsList", () => {
  beforeEach(() => {
    resetLineage();
  });

  afterEach(() => {
    cleanup();
    resetLineage();
  });

  it("renders one row per run", () => {
    useAppStore.setState({
      runs: [makeRun({ run_id: "r1" }), makeRun({ run_id: "r2" })],
    });
    render(<RunsList />);
    expect(screen.getByTestId("runs-list-row-r1")).toBeInTheDocument();
    expect(screen.getByTestId("runs-list-row-r2")).toBeInTheDocument();
  });

  it("dispatches selectRun on row click", () => {
    const selectRunSpy = vi.fn();
    useAppStore.setState({
      runs: [makeRun({ run_id: "r1" })],
      selectRun: selectRunSpy,
    });
    render(<RunsList />);
    fireEvent.click(screen.getByTestId("runs-list-row-r1"));
    expect(selectRunSpy).toHaveBeenCalledWith("r1");
  });

  it("marks the selected row with aria-selected=true", () => {
    useAppStore.setState({
      runs: [makeRun({ run_id: "r1" })],
      selectedRunId: "r1",
    });
    render(<RunsList />);
    expect(
      screen.getByTestId("runs-list-row-r1").getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("renders the empty placeholder when runs is empty", () => {
    render(<RunsList />);
    expect(screen.getByTestId("runs-list-empty")).toBeInTheDocument();
  });

  it("shows the re-run marker for runs with parent_run_id", () => {
    useAppStore.setState({
      runs: [
        makeRun({
          parent_run_id: "deadbeefcafef00d",
          execute_from_block_id: "threshold_1",
        }),
      ],
    });
    render(<RunsList />);
    const marker = screen.getByTestId("rerun-marker");
    expect(marker.textContent).toContain("deadbeef");
    expect(marker.textContent).toContain("threshold_1");
  });

  it("omits the block count when block_count is null (Codex P2)", () => {
    useAppStore.setState({
      runs: [makeRun({ run_id: "r-null", block_count: null })],
    });
    render(<RunsList />);
    const row = screen.getByTestId("runs-list-row-r-null");
    expect(row.textContent).not.toMatch(/block\(s\)/);
  });

  it("renders a colored status pill for each status (hotfix #998)", () => {
    /*
     * Hotfix #998: the row's primary visual is now a colored pill
     * carrying the status name as visible text (not sr-only). The
     * `StatusIcon` glyph + sr-only pattern was removed from rows
     * because the pill text is directly readable by screen readers.
     * Assert that each status renders its pill with the right
     * background-color class.
     */
    const expected: Array<[LineageRunSummary["status"], string]> = [
      ["completed", "bg-emerald-600"],
      ["failed", "bg-rose-600"],
      ["cancelled", "bg-slate-500"],
      ["running", "bg-amber-500"],
    ];
    for (const [status, bgClass] of expected) {
      useAppStore.setState({
        runs: [
          makeRun({
            run_id: `s-${status}`,
            status,
            finished_at: status === "running" ? null : "2026-05-15T14:30:12Z",
            duration_ms: status === "running" ? null : 12000,
          }),
        ],
      });
      const { unmount } = render(<RunsList />);
      const pill = screen.getByTestId(`runs-list-row-s-${status}-status-pill`);
      expect(pill).toBeInTheDocument();
      expect(pill).toHaveTextContent(status);
      expect(pill.className).toMatch(new RegExp(bgClass));
      unmount();
      cleanup();
    }
  });
});
