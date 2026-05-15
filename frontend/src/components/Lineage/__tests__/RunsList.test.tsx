/*
 * RunsList.test.tsx — D38-2.4b skeleton test plan
 * ===============================================
 *
 * All cases use it.skip(...). IMPL D38-2.4c fills bodies.
 *
 * Test plan (mirrors RunsList.tsx "Test plan" section):
 *   1. renders one row per run with [data-testid=runs-list-row-{run_id}]
 *   2. clicking a row dispatches selectRun(run_id)
 *   3. selected row has aria-selected="true"
 *   4. empty state renders [data-testid=runs-list-empty]
 *   5. parent_run_id renders [data-testid=rerun-marker]
 *   6. status icon has sr-only text matching run.status
 *   7. running row updates duration once per second (vi.useFakeTimers)
 *
 * Fixtures
 * --------
 * Helper to build LineageRunSummary with sane defaults:
 *
 *   const makeRun = (overrides: Partial<LineageRunSummary> = {}): LineageRunSummary => ({
 *     run_id: "00000000-0000-0000-0000-000000000001",
 *     workflow_id: "image_pipeline",
 *     workflow_git_commit: "abc1234567",
 *     workflow_dirty: false,
 *     started_at: "2026-05-15T14:30:00Z",
 *     finished_at: "2026-05-15T14:30:12Z",
 *     status: "completed",
 *     triggered_by: "user",
 *     parent_run_id: null,
 *     execute_from_block_id: null,
 *     block_count: 4,
 *     duration_ms: 12000,
 *     ...overrides,
 *   });
 */

import { describe, it } from "vitest";

describe("RunsList", () => {
  it.skip("renders one row per run", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with runs=[makeRun({run_id: "r1"}), makeRun({run_id: "r2"})].
     *   2. Render <RunsList />.
     *   3. Expect getByTestId("runs-list-row-r1") and "runs-list-row-r2".
     */
  });

  it.skip("dispatches selectRun on row click", async () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with runs=[makeRun({run_id:"r1"})], selectRun=vi.fn().
     *   2. Render and click the row.
     *   3. Expect selectRun to have been called with "r1".
     */
  });

  it.skip("marks the selected row with aria-selected=true", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with runs=[makeRun({run_id:"r1"})], selectedRunId="r1".
     *   2. Render <RunsList />.
     *   3. Expect getByTestId("runs-list-row-r1").getAttribute("aria-selected")
     *      to equal "true".
     */
  });

  it.skip("renders the empty placeholder when runs is empty", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with runs=[], runsLoading=false.
     *   2. Render <RunsList />.
     *   3. Expect getByTestId("runs-list-empty") with the empty-state copy.
     */
  });

  it.skip("shows the re-run marker for runs with parent_run_id", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with runs=[makeRun({
     *        parent_run_id: "deadbeef-...",
     *        execute_from_block_id: "threshold_1",
     *      })].
     *   2. Render <RunsList />.
     *   3. Expect getByTestId("rerun-marker") with text including the parent
     *      short id and "from threshold_1".
     */
  });

  it.skip("renders sr-only text for the status icon", () => {
    /* IMPL D38-2.4c:
     *   For each of "completed" / "failed" / "cancelled" / "running":
     *   1. Render with one row of that status.
     *   2. Expect a span.sr-only descendant whose textContent ===
     *      run.status (e.g., "completed").
     */
  });

  it.skip("ticks the live duration counter for running rows", () => {
    /* IMPL D38-2.4c:
     *   1. vi.useFakeTimers(); set Date.now to a known value.
     *   2. Render <RunsList /> with runs=[makeRun({
     *        status: "running",
     *        finished_at: null,
     *        duration_ms: null,
     *        started_at: <now-3s>,
     *      })].
     *   3. Expect row to show "3s".
     *   4. vi.advanceTimersByTime(1000).
     *   5. Expect row to show "4s".
     *   6. vi.useRealTimers().
     */
  });
});
