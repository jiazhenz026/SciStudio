/*
 * frontend/src/store/lineageSlice.ts — ADR-038 §3.8 Lineage UI client state
 * ========================================================================
 *
 * SKELETON ONLY. Function bodies throw `new Error("TODO: D38-2.4c — ...")`.
 * The D38-2.4c IMPL agent must fill in the bodies using ONLY these comments
 * as the spec — do not improvise behaviour, do not silently relax contracts.
 *
 * Purpose
 * -------
 * Client-side cache + interaction state for the Lineage tab (per ADR-038
 * §3.8). The runtime source of truth lives in `<project>/.scieasy/lineage.db`
 * and is exposed over REST by `src/scieasy/api/routes/runs.py` (D38-2.4a).
 * This slice does NOT mutate lineage data — it caches what the server
 * returns and tracks UI state (selection, loading flags, error strings).
 *
 * State shape
 * -----------
 *
 *   interface LineageRunSummary {
 *     run_id:                  string;     // UUIDv4
 *     workflow_id:             string;     // logical name e.g. "image_pipeline"
 *     workflow_git_commit:     string | null;   // ADR-039 SHA at run start
 *     workflow_dirty:          boolean;
 *     started_at:              string;     // ISO-8601
 *     finished_at:             string | null;
 *     status:                  "running" | "completed" | "failed" | "cancelled";
 *     triggered_by:            "user" | "ai_block" | "execute_from";
 *     parent_run_id:           string | null;
 *     execute_from_block_id:   string | null;
 *     block_count:             number;     // convenience, server-computed
 *     duration_ms:             number | null;   // null while running
 *   }
 *
 *   interface LineageBlockExecution {
 *     block_execution_id:    string;
 *     block_id:              string;      // DAG node id, e.g. "load_image_1"
 *     block_type:            string;      // class name
 *     block_version:         string;      // force-injected per ADR-038 §3.3
 *     block_config_resolved: Record<string, unknown>;  // post-template-expansion
 *     started_at:            string;
 *     finished_at:           string | null;
 *     duration_ms:           number | null;
 *     termination:           "completed" | "error" | "cancelled" | "skipped";
 *     termination_detail:    string | null;
 *     // I/O references (ADR-038 §3.1 block_io table joined with data_objects)
 *     inputs:  LineageDataObjectRef[];
 *     outputs: LineageDataObjectRef[];
 *   }
 *
 *   interface LineageDataObjectRef {
 *     object_id:      string;
 *     type_name:      string;            // "Image" / "DataFrame" / ...
 *     port_name:      string;
 *     position:       number;            // collection index within port
 *     storage_path:   string | null;     // best-effort; may be stale
 *     // Note: wire_payload is NOT cached on the client — fetched on demand
 *     // by RunDetail when the user expands a block I/O row. See ADR-038 §3.5
 *     // (storage_path is best-effort, NOT a guarantee of file presence).
 *   }
 *
 *   interface LineageRunDetail {
 *     run:           LineageRunSummary;
 *     blocks:        LineageBlockExecution[];   // ordered by started_at
 *     // Full YAML snapshot lives server-side in runs.workflow_yaml_snapshot
 *     // (ADR-038 §3.1) — fetched on demand by RunDetail "View workflow YAML"
 *     // affordance. Not cached here to keep slice size bounded.
 *     environment_snapshot: Record<string, string>;  // package -> version
 *     workflow_yaml_snapshot: string | null;          // populated lazily
 *   }
 *
 *   interface LineageSlice {
 *     // ---- list pane ---------------------------------------------------
 *     runs:           LineageRunSummary[];
 *     runsLoading:    boolean;
 *     runsError:      string | null;        // last fetch error (transient)
 *     // ---- detail pane -------------------------------------------------
 *     selectedRunId:  string | null;        // matches a row in `runs` OR a
 *                                           // stale id (race after re-run)
 *     runDetails:     Record<string, LineageRunDetail>;  // cache keyed by run_id
 *     runDetailLoading: Record<string, boolean>;          // per-run flag
 *     runDetailError:   Record<string, string | null>;
 *     // ---- per-block expansion (UI-only) -------------------------------
 *     expandedBlockExecutionIds: string[];  // BlockExecutionCard "expanded"
 *     // ---- dialogs (UI-only) -------------------------------------------
 *     methodsDialogRunId: string | null;     // null = closed
 *     rerunDialogRunId:   string | null;     // null = closed
 *     // ---- actions -----------------------------------------------------
 *     fetchRuns:      (opts?: { workflowId?: string; limit?: number }) => Promise<void>;
 *     fetchRunDetail: (runId: string) => Promise<void>;
 *     selectRun:      (runId: string | null) => void;
 *     toggleBlockExecutionExpanded: (blockExecutionId: string) => void;
 *     openMethodsDialog: (runId: string) => void;
 *     closeMethodsDialog: () => void;
 *     openRerunDialog: (runId: string) => void;
 *     closeRerunDialog: () => void;
 *     // Lifecycle: clear caches on project switch (App.tsx subscribes to
 *     // currentProject change and calls this to flush stale runs).
 *     clearLineage: () => void;
 *   }
 *
 * Action semantics
 * ----------------
 *
 *   fetchRuns(opts):
 *     - set runsLoading=true, runsError=null
 *     - call api.lineage.getRuns(opts)
 *     - on success: set runs=response, runsLoading=false
 *     - on failure: set runsError=message, runsLoading=false (keep stale runs)
 *     - debounce: caller responsibility — slice does NOT auto-debounce
 *
 *   fetchRunDetail(runId):
 *     - set runDetailLoading[runId]=true, runDetailError[runId]=null
 *     - call api.lineage.getRun(runId)
 *     - on success: write runDetails[runId]=response; clear loading
 *     - on 404: set runDetailError[runId]="Run not found" (do NOT delete key —
 *       lets RunDetail render the error inline)
 *     - on other failure: set runDetailError[runId]=message
 *
 *   selectRun(runId):
 *     - set selectedRunId=runId
 *     - if runId !== null AND runDetails[runId] === undefined → call
 *       fetchRunDetail(runId)
 *     - if runId === null → no fetch (clears right pane)
 *
 *   toggleBlockExecutionExpanded(id):
 *     - flip presence of `id` in expandedBlockExecutionIds (immutable patch)
 *     - bounded: no LRU eviction at this scope; the per-run blocks list is
 *       small (<100 typical). If a future run exceeds 500 blocks, this set
 *       still fits in memory.
 *
 *   openMethodsDialog / openRerunDialog:
 *     - set the corresponding *DialogRunId field
 *     - if details aren't cached, ALSO call fetchRunDetail — dialogs render
 *       fields straight from runDetails[runId]
 *
 *   clearLineage:
 *     - reset every field to its initial value
 *     - called by projectSlice.setCurrentProject when the project changes
 *
 * Loading-state contract
 * ----------------------
 *
 * The list pane and detail pane have independent loading flags so a slow
 * detail fetch does not blank the list. Components MUST treat
 * `runDetailLoading[selectedRunId] === true` as "right pane is mid-fetch"
 * and render a spinner WITHOUT unmounting the previously-rendered detail
 * (see RunDetail comments for the placeholder skeleton).
 *
 * Error-state contract
 * --------------------
 *
 * Errors are STRINGS, not Error instances. The lib/api.ts layer normalizes
 * ApiError into `error.message` before this slice sees it. UI components
 * may surface as toast OR inline; they do NOT need to reason about HTTP
 * status codes here (api.ts already maps 404 / 500 / network failure to
 * human strings).
 *
 * Stale-data contract
 * -------------------
 *
 * When a websocket "run_completed" event fires (OQ-5 in ADR-038 §8 —
 * deferred to D38-2.4c implementation), the IMPL agent will dispatch
 * `fetchRuns()` to refresh the list. This slice does NOT subscribe to the
 * websocket itself — that wiring lives in `frontend/src/hooks/useWebSocket.ts`
 * (per ADR-039 §3.8 we already own a `git.head_changed` event; the lineage
 * counterpart is OQ-5 + a follow-up issue if needed).
 *
 * Edge cases the IMPL must handle
 * --------------------------------
 *   1. Running run shows in list with `status === "running"` and a live
 *      duration counter (computed client-side from started_at; do NOT mutate
 *      duration_ms because that's server-authoritative).
 *   2. Failed fetchRunDetail leaves stale data in runDetails[runId] visible
 *      — the IMPL must NOT delete it on error so the user sees "stale +
 *      error message", not "blank + error message".
 *   3. selectRun on a runId that doesn't exist in `runs` (e.g. deep-linked
 *      URL) must still attempt fetchRunDetail; the server returns 404 and
 *      the right pane renders the error.
 *   4. clearLineage MUST NOT trigger any in-flight fetches' resolve()
 *      callbacks to clobber the cleared state — IMPL should track a
 *      generation counter or AbortController and ignore stale responses.
 *      (Acceptable simplification for v1: ignore — the race window is tiny
 *      and the symptom is benign. Document in IMPL PR.)
 *
 * Accessibility / keyboard
 * ------------------------
 * Slice has no a11y obligations (components own ARIA). Keyboard shortcuts
 * are owned by LineageTab (see its top-of-file comments).
 *
 * Test plan (lives in __tests__/lineageSlice.test.ts as it.skip docstrings)
 * -----------------------------------------------------------------------
 *   1. initial state: runs=[], runsLoading=false, selectedRunId=null
 *   2. fetchRuns: success path populates runs, clears loading
 *   3. fetchRuns: failure path sets runsError, preserves prior runs
 *   4. fetchRunDetail: writes to runDetails keyed by run_id
 *   5. selectRun: triggers fetchRunDetail on cache miss, no fetch on hit
 *   6. toggleBlockExecutionExpanded: idempotent toggle
 *   7. clearLineage: full reset
 */

import type { StateCreator } from "zustand";

import { ApiError, api } from "../lib/api";
import type { LineageRunDetail, LineageRunSummary } from "../types/lineage";
import type { AppStore } from "./types";

// Re-export wire-shape types (single source: `types/lineage.ts`) so
// components and tests can import either from this slice OR from
// types/lineage. Both surfaces are stable.
export type {
  LineageBlockExecution,
  LineageDataObjectRef,
  LineageRunDetail,
  LineageRunStatus,
  LineageBlockTermination,
  LineageRunSummary,
} from "../types/lineage";

export interface LineageSlice {
  // list pane
  runs: LineageRunSummary[];
  runsLoading: boolean;
  runsError: string | null;
  // detail pane
  selectedRunId: string | null;
  runDetails: Record<string, LineageRunDetail>;
  runDetailLoading: Record<string, boolean>;
  runDetailError: Record<string, string | null>;
  // per-block expansion (UI-only)
  expandedBlockExecutionIds: string[];
  // dialogs (UI-only)
  methodsDialogRunId: string | null;
  rerunDialogRunId: string | null;
  // actions
  fetchRuns: (opts?: { workflowId?: string; limit?: number }) => Promise<void>;
  fetchRunDetail: (runId: string) => Promise<void>;
  selectRun: (runId: string | null) => void;
  toggleBlockExecutionExpanded: (blockExecutionId: string) => void;
  openMethodsDialog: (runId: string) => void;
  closeMethodsDialog: () => void;
  openRerunDialog: (runId: string) => void;
  closeRerunDialog: () => void;
  clearLineage: () => void;
}

const INITIAL_LINEAGE_STATE = {
  runs: [] as LineageRunSummary[],
  runsLoading: false,
  runsError: null as string | null,
  selectedRunId: null as string | null,
  runDetails: {} as Record<string, LineageRunDetail>,
  runDetailLoading: {} as Record<string, boolean>,
  runDetailError: {} as Record<string, string | null>,
  expandedBlockExecutionIds: [] as string[],
  methodsDialogRunId: null as string | null,
  rerunDialogRunId: null as string | null,
};

export const createLineageSlice: StateCreator<AppStore, [], [], LineageSlice> = (
  set,
  get,
) => ({
  ...INITIAL_LINEAGE_STATE,

  fetchRuns: async (opts) => {
    set({ runsLoading: true, runsError: null });
    try {
      const { runs } = await api.lineage.getRuns(opts);
      set({ runs, runsLoading: false });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load runs";
      // Keep previously-loaded runs visible; only flip loading + error.
      set({ runsLoading: false, runsError: message });
    }
  },

  fetchRunDetail: async (runId) => {
    set((s) => ({
      runDetailLoading: { ...s.runDetailLoading, [runId]: true },
      runDetailError: { ...s.runDetailError, [runId]: null },
    }));
    try {
      const detail = await api.lineage.getRun(runId);
      set((s) => ({
        runDetails: { ...s.runDetails, [runId]: detail },
        runDetailLoading: { ...s.runDetailLoading, [runId]: false },
        runDetailError: { ...s.runDetailError, [runId]: null },
      }));
    } catch (err) {
      const isNotFound =
        err instanceof ApiError && err.status === 404
          ? "Run not found"
          : null;
      const message =
        isNotFound ??
        (err instanceof Error ? err.message : "Failed to load run detail");
      set((s) => ({
        runDetailLoading: { ...s.runDetailLoading, [runId]: false },
        runDetailError: { ...s.runDetailError, [runId]: message },
      }));
    }
  },

  selectRun: (runId) => {
    set({ selectedRunId: runId });
    if (runId === null) return;
    const state = get();
    if (state.runDetails[runId] === undefined) {
      void state.fetchRunDetail(runId);
    }
  },

  toggleBlockExecutionExpanded: (blockExecutionId) => {
    set((s) => {
      const present = s.expandedBlockExecutionIds.includes(blockExecutionId);
      return {
        expandedBlockExecutionIds: present
          ? s.expandedBlockExecutionIds.filter((id) => id !== blockExecutionId)
          : [...s.expandedBlockExecutionIds, blockExecutionId],
      };
    });
  },

  openMethodsDialog: (runId) => {
    set({ methodsDialogRunId: runId });
    const state = get();
    if (state.runDetails[runId] === undefined) {
      void state.fetchRunDetail(runId);
    }
  },

  closeMethodsDialog: () => {
    set({ methodsDialogRunId: null });
  },

  openRerunDialog: (runId) => {
    set({ rerunDialogRunId: runId });
    const state = get();
    if (state.runDetails[runId] === undefined) {
      void state.fetchRunDetail(runId);
    }
  },

  closeRerunDialog: () => {
    set({ rerunDialogRunId: null });
  },

  clearLineage: () => {
    set({ ...INITIAL_LINEAGE_STATE });
  },
});
