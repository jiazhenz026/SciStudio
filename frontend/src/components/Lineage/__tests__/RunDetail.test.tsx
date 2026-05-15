/*
 * RunDetail.test.tsx — D38-2.4b skeleton test plan
 * ================================================
 *
 * All cases use it.skip(...). IMPL D38-2.4c fills bodies.
 *
 * Test plan (mirrors RunDetail.tsx "Test plan" section):
 *   1. selectedRunId===null renders [data-testid=run-detail-empty]
 *   2. loading state renders [data-testid=run-detail-loading]
 *   3. error state renders [data-testid=run-detail-error]
 *   4. happy path renders [data-testid=run-detail] with header + blocks
 *   5. Re-run button dispatches openRerunDialog
 *   6. Export methods button dispatches openMethodsDialog
 *   7. running status disables Re-run button
 *   8. parent_run_id renders a "Parent run" row
 *
 * BlockExecutionCard interactions (covered here, no separate file):
 *   9. clicking the toggle expands/collapses the body
 *  10. error termination renders [data-testid=block-card-error]
 *
 * Fixtures
 * --------
 *   const makeDetail = (overrides: Partial<LineageRunDetail> = {}): LineageRunDetail => ({
 *     run: makeRun(),
 *     blocks: [makeBlock()],
 *     environment_snapshot: { scieasy: "0.1.0" },
 *     workflow_yaml_snapshot: "id: image_pipeline\nblocks: []\n",
 *     ...overrides,
 *   });
 *
 *   const makeBlock = (overrides: Partial<LineageBlockExecution> = {}): LineageBlockExecution => ({
 *     block_execution_id: "be-001",
 *     block_id: "load_image_1",
 *     block_type: "LoadImage",
 *     block_version: "0.1.0",
 *     block_config_resolved: { path: "/tmp/img.tif" },
 *     started_at: "2026-05-15T14:30:00Z",
 *     finished_at: "2026-05-15T14:30:03Z",
 *     duration_ms: 3000,
 *     termination: "completed",
 *     termination_detail: null,
 *     inputs: [],
 *     outputs: [{
 *       object_id: "obj-xyz",
 *       type_name: "Image",
 *       port_name: "image",
 *       position: 0,
 *       storage_path: "/tmp/img.zarr",
 *     }],
 *     ...overrides,
 *   });
 */

import { describe, it } from "vitest";

describe("RunDetail", () => {
  it.skip("renders the empty state when no run selected", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with selectedRunId=null.
     *   2. Render <RunDetail />.
     *   3. Expect getByTestId("run-detail-empty").
     */
  });

  it.skip("renders the loading state while the detail is fetching", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with selectedRunId="r1", runDetailLoading={r1:true},
     *      runDetails={}.
     *   2. Render <RunDetail />.
     *   3. Expect getByTestId("run-detail-loading").
     */
  });

  it.skip("renders the error state when fetch failed", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with selectedRunId="r1", runDetailError={r1:"Not found"}.
     *   2. Render <RunDetail />.
     *   3. Expect getByTestId("run-detail-error") with text "Not found".
     */
  });

  it.skip("renders the happy path with header + blocks list", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with selectedRunId="r1", runDetails={r1: makeDetail()}.
     *   2. Render <RunDetail />.
     *   3. Expect getByTestId("run-detail").
     *   4. Expect getByTestId("run-detail-blocks") to contain one
     *      BlockExecutionCard (data-testid="block-execution-card-be-001").
     */
  });

  it.skip("dispatches openRerunDialog when Re-run clicked", async () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with detail loaded, openRerunDialog=vi.fn().
     *   2. Render and click getByTestId("run-detail-rerun-button").
     *   3. Expect openRerunDialog called with the run_id.
     */
  });

  it.skip("dispatches openMethodsDialog when Export methods clicked", async () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with detail loaded, openMethodsDialog=vi.fn().
     *   2. Render and click getByTestId("run-detail-methods-button").
     *   3. Expect openMethodsDialog called with the run_id.
     */
  });

  it.skip("disables Re-run button when run is still running", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with detail.run.status="running" and finished_at=null.
     *   2. Render <RunDetail />.
     *   3. Expect getByTestId("run-detail-rerun-button").getAttribute(
     *        "aria-disabled") to equal "true" (or disabled attribute set).
     */
  });

  it.skip("renders the Parent run row when parent_run_id is set", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with detail.run.parent_run_id="dead-beef-abcd-1234".
     *   2. Render <RunDetail />.
     *   3. Expect getByText("Parent run") and the dd to contain
     *      "dead-bee" (first 8 chars).
     */
  });

  it.skip("expands a BlockExecutionCard body on toggle", async () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with detail loaded, toggleBlockExecutionExpanded=vi.fn(),
     *      expandedBlockExecutionIds=[].
     *   2. Render <RunDetail />.
     *   3. Click getByTestId("block-execution-card-toggle-be-001").
     *   4. Expect toggleBlockExecutionExpanded called with "be-001".
     */
  });

  it.skip("renders block error section when termination is 'error'", () => {
    /* IMPL D38-2.4c:
     *   1. Mock store with one block having termination="error" and
     *      termination_detail="boom".
     *   2. Force the card expanded (expandedBlockExecutionIds=["be-001"]).
     *   3. Render <RunDetail />.
     *   4. Expect getByTestId("block-card-error") with text "boom".
     */
  });
});
