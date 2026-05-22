/*
 * frontend/src/types/lineage.ts — ADR-038 §3.1/§3.7 wire-shape types
 * ==================================================================
 *
 * Single source of truth for the Lineage REST surface types. Imported by
 * both `lib/api.ts` (API client) and `store/lineageSlice.ts` (state
 * cache), so this module deliberately depends on NOTHING else in the
 * frontend tree — keeps the import graph acyclic.
 *
 * These shapes mirror the SQL schema in ADR-038 §3.1 with one
 * de-normalization step: the SELECT for `GET /api/runs/{run_id}` joins
 * block_io + data_objects so each LineageBlockExecution surfaces inputs
 * and outputs as already-hydrated rows rather than separate references.
 *
 * Authoritative endpoint shapes per ADR-038 §3.8:
 *   GET  /api/runs?workflow_id=...&limit=...
 *   GET  /api/runs/{run_id}
 *   GET  /api/runs/{run_id}/methods
 *   GET  /api/runs/{run_id}/validate-rerun
 *   POST /api/runs/{run_id}/rerun
 *
 * D38-2.4a (parallel backend skeleton) owns the FastAPI route signatures
 * in `src/scistudio/api/routes/runs.py`. Both PRs target the tracking
 * branch `track/adr-038/lineage-db`; if the backend refines the response
 * envelope before D38-2.4c IMPL, the IMPL agent updates this file.
 */

export type LineageRunStatus = "running" | "completed" | "failed" | "cancelled";
export type LineageBlockTermination = "completed" | "error" | "cancelled" | "skipped";

/**
 * One row from the `runs` table (ADR-038 §3.1) plus a computed
 * `block_count` convenience field. The runs list pane displays this shape.
 */
export interface LineageRunSummary {
  run_id: string;
  workflow_id: string;
  workflow_git_commit: string | null;
  workflow_dirty: boolean;
  started_at: string;
  finished_at: string | null;
  status: LineageRunStatus;
  triggered_by: "user" | "ai_block" | "execute_from";
  parent_run_id: string | null;
  execute_from_block_id: string | null;
  /**
   * Number of ``block_executions`` rows for this run, or ``null`` when
   * the backend list endpoint omits the column (it does today —
   * ``GET /api/runs`` returns raw ``runs`` rows without a join).
   * ``LineageRunDetail.blocks.length`` is the authoritative count once
   * the detail loads; the frontend back-fills ``block_count`` from there.
   */
  block_count: number | null;
  duration_ms: number | null;
}

/**
 * One I/O edge from the join of `block_io` + `data_objects` (ADR-038 §3.1).
 * `position` is the index within the port (Collection items become
 * separate rows per §3.1 unrolling rule).
 */
export interface LineageDataObjectRef {
  object_id: string;
  type_name: string;
  port_name: string;
  position: number;
  storage_path: string | null;
}

/** One row from `block_executions` joined with `block_io` (inputs/outputs). */
export interface LineageBlockExecution {
  block_execution_id: string;
  block_id: string;
  block_type: string;
  block_version: string;
  block_config_resolved: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  termination: LineageBlockTermination;
  termination_detail: string | null;
  inputs: LineageDataObjectRef[];
  outputs: LineageDataObjectRef[];
}

/** Top-level shape returned by `GET /api/runs/{run_id}`. */
export interface LineageRunDetail {
  run: LineageRunSummary;
  blocks: LineageBlockExecution[];
  environment_snapshot: Record<string, string>;
  workflow_yaml_snapshot: string | null;
}

// --- Endpoint envelopes ----------------------------------------------------

export interface LineageGetRunsParams {
  workflowId?: string;
  limit?: number;
}
export interface LineageGetRunsResponse {
  runs: LineageRunSummary[];
}
export interface LineageMethodsResponse {
  markdown: string;
}
export interface LineageRerunInputWarning {
  path: string;
  reason: string;
}
export interface LineageRerunEnvWarning {
  package: string;
  old: string;
  new: string;
}
export interface LineageRerunValidation {
  input_warnings: LineageRerunInputWarning[];
  env_warnings: LineageRerunEnvWarning[];
}
export interface LineageRerunResponse {
  /** UUID of the new run record created by the backend re-execution. */
  new_run_id: string;
}
