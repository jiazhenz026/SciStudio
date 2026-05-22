import type {
  BlockListResponse,
  BlockSchemaResponse,
  CancelPropagationResponse,
  ConnectionValidationResponse,
  DataMetadataResponse,
  DataPreviewQuery,
  DataPreviewResponse,
  DataUploadResponse,
  ExecuteFromResponse,
  FilesystemBrowseResponse,
  GitBranch,
  GitCommit,
  GitCommitResponse,
  GitDiff,
  GitMergeResult,
  GitRestoreResult,
  GitStatus,
  ProjectResponse,
  TreeResponse,
  WorkflowExecutionResponse,
  WorkflowResponse,
} from "../types/api";
import type {
  LineageBlockExecution,
  LineageDataObjectRef,
  LineageGetRunsParams,
  LineageGetRunsResponse,
  LineageMethodsResponse,
  LineageRerunResponse,
  LineageRerunValidation,
  LineageRunDetail,
  LineageRunSummary,
} from "../types/lineage";

const JSON_HEADERS = {
  "Content-Type": "application/json",
};

export type VersionedWorkflowResponse = WorkflowResponse & {
  state_version?: number;
  workflow_version?: string;
  entity_class?: "workflow";
  entity_id?: string;
  source?: string | null;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
};

export interface ProjectFileResponse {
  content: string;
  mtime: number;
  size: number;
  encoding: string;
  state_version?: number;
  entity_class?: "file";
  entity_id?: string;
  source?: string | null;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
}

export interface ProjectFileWriteResponse {
  mtime: number;
  size: number;
  state_version?: number;
  entity_class?: "file";
  entity_id?: string;
  source?: string;
  source_id?: string | null;
  kind?: string;
  timestamp?: string;
}

export interface VersionedWriteOptions {
  sourceId?: string;
  source?: "canvas" | "agent" | "gitRestore" | "import" | "external" | string;
}

const pendingWorkflowSourceIds = new Map<string, Set<string>>();
let workflowWriteStartedListener: ((workflowId: string, sourceId: string) => void) | null =
  null;

export function createClientSourceId(prefix: "workflow" | "file"): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  const token =
    typeof randomUUID === "function"
      ? randomUUID.call(globalThis.crypto)
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${token}`;
}

export function setWorkflowWriteStartedListener(
  listener: ((workflowId: string, sourceId: string) => void) | null,
): void {
  workflowWriteStartedListener = listener;
}

function rememberPendingWorkflowSourceId(workflowId: string, sourceId: string): void {
  const existing = pendingWorkflowSourceIds.get(workflowId) ?? new Set<string>();
  existing.add(sourceId);
  pendingWorkflowSourceIds.set(workflowId, existing);
  workflowWriteStartedListener?.(workflowId, sourceId);
}

export function consumePendingWorkflowSourceId(workflowId: string, sourceId: string | null): boolean {
  if (!sourceId) return false;
  const existing = pendingWorkflowSourceIds.get(workflowId);
  if (!existing?.has(sourceId)) return false;
  existing.delete(sourceId);
  if (existing.size === 0) pendingWorkflowSourceIds.delete(workflowId);
  return true;
}

/**
 * Error thrown by `apiFetch` for non-2xx responses. Exposes the HTTP status
 * code so callers can branch on it (e.g. fall back on 500 but not on 504).
 * See issue #678.
 */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({ detail: response.statusText }))) as {
      detail?: string | { message?: string; errors?: unknown };
    };
    // ``detail`` can be a plain string (legacy + FastAPI default) OR a
    // structured object like ``{message, errors}`` (used by the workflow
    // GET route when a YAML fails pydantic validation — surfaces the
    // exact field/reason list for the agent / GUI to display).
    let message: string;
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (payload.detail && typeof payload.detail.message === "string") {
      message = payload.detail.message;
    } else {
      message = `Request failed with ${response.status}`;
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects: () => apiFetch<ProjectResponse[]>("/api/projects/"),
  createProject: (body: { name: string; description: string; path: string }) =>
    apiFetch<ProjectResponse>("/api/projects/", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  openProject: (projectIdOrPath: string) =>
    apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(projectIdOrPath)}`),
  updateProject: (projectId: string, body: { name?: string; description?: string }) =>
    apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  deleteProject: (projectId: string) =>
    apiFetch<void>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    }),
  listBlocks: () => apiFetch<BlockListResponse>("/api/blocks/"),
  getBlockSchema: (blockType: string) =>
    apiFetch<BlockSchemaResponse>(`/api/blocks/${encodeURIComponent(blockType)}/schema`),
  validateConnection: (body: {
    source_block: string;
    source_port: string;
    target_block: string;
    target_port: string;
  }) =>
    apiFetch<ConnectionValidationResponse>("/api/blocks/validate-connection", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  listWorkflows: () => apiFetch<string[]>("/api/workflows/list"),
  importWorkflowFile: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<VersionedWorkflowResponse>("/api/workflows/import", {
      method: "POST",
      body: formData,
    });
  },
  importWorkflowFromPath: async (filePath: string) => {
    // Read the file via fetch from the backend browse result, then re-upload
    // For now, use a dedicated endpoint that accepts a path
    // TODO: replace the dedicated /api/workflows/import-path endpoint with a fetch-then-import flow that reuses /api/projects/{id}/file.
    return apiFetch<VersionedWorkflowResponse>("/api/workflows/import-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path: filePath }),
    });
  },
  createWorkflow: async (body: WorkflowResponse, options?: VersionedWriteOptions) => {
    const sourceId = options?.sourceId ?? createClientSourceId("workflow");
    rememberPendingWorkflowSourceId(body.id, sourceId);
    return apiFetch<VersionedWorkflowResponse>("/api/workflows/", {
      method: "POST",
      headers: {
        ...JSON_HEADERS,
        "X-Source-Id": sourceId,
        "X-Workflow-Source": options?.source ?? "canvas",
      },
      body: JSON.stringify(body),
    });
  },
  getWorkflow: (workflowId: string) =>
    apiFetch<VersionedWorkflowResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`),
  updateWorkflow: async (workflowId: string, body: WorkflowResponse, options?: VersionedWriteOptions) => {
    const sourceId = options?.sourceId ?? createClientSourceId("workflow");
    rememberPendingWorkflowSourceId(workflowId, sourceId);
    return apiFetch<VersionedWorkflowResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
      method: "PUT",
      headers: {
        ...JSON_HEADERS,
        "X-Source-Id": sourceId,
        "X-Workflow-Source": options?.source ?? "canvas",
      },
      body: JSON.stringify(body),
    });
  },
  deleteWorkflow: (workflowId: string) =>
    apiFetch<void>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
      method: "DELETE",
    }),
  executeWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/execute`, {
      method: "POST",
    }),
  pauseWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/pause`, {
      method: "POST",
    }),
  resumeWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/resume`, {
      method: "POST",
    }),
  cancelWorkflow: (workflowId: string) =>
    apiFetch<CancelPropagationResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/cancel`, {
      method: "POST",
    }),
  cancelBlock: (workflowId: string, blockId: string) =>
    apiFetch<CancelPropagationResponse>(
      `/api/workflows/${encodeURIComponent(workflowId)}/blocks/${encodeURIComponent(blockId)}/cancel`,
      { method: "POST" },
    ),
  executeFrom: (workflowId: string, blockId: string) =>
    apiFetch<ExecuteFromResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/execute-from`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ block_id: blockId }),
    }),
  uploadData: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DataUploadResponse>("/api/data/upload", {
      method: "POST",
      body: formData,
    });
  },
  getDataMetadata: (dataRef: string) => apiFetch<DataMetadataResponse>(`/api/data/${encodeURIComponent(dataRef)}`),
  getDataPreview: (dataRef: string, opts?: number | DataPreviewQuery) => {
    // Backwards-compat: a bare number is interpreted as ``slice`` (image flow).
    // Object form covers slice + DataFrame paging (page/page_size/sort_by/sort_dir).
    const o: DataPreviewQuery = typeof opts === "number" ? { slice: opts } : (opts ?? {});
    const params = new URLSearchParams();
    if (o.slice !== undefined) params.set("slice", String(o.slice));
    if (o.page !== undefined) params.set("page", String(o.page));
    if (o.pageSize !== undefined) params.set("page_size", String(o.pageSize));
    if (o.sortBy) params.set("sort_by", o.sortBy);
    if (o.sortDir) params.set("sort_dir", o.sortDir);
    const qs = params.toString();
    const url = `/api/data/${encodeURIComponent(dataRef)}/preview${qs ? `?${qs}` : ""}`;
    return apiFetch<DataPreviewResponse>(url);
  },
  browseFilesystem: (path: string) =>
    apiFetch<FilesystemBrowseResponse>(
      `/api/filesystem/browse?path=${encodeURIComponent(path)}`,
    ),
  getProjectTree: (projectId: string, path = "") =>
    apiFetch<TreeResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/tree?path=${encodeURIComponent(path)}`,
    ),
  revealInExplorer: (path: string) =>
    apiFetch<{ status: string }>("/api/filesystem/reveal", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path }),
    }),
  openNativeDialog: (mode: "file" | "directory", initialDir?: string) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ mode, initial_dir: initialDir }),
    }),
  openNativeSaveDialog: (options: { initialDir?: string; defaultFilename?: string; fileFilter?: string }) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        mode: "save_file",
        initial_dir: options.initialDir,
        default_filename: options.defaultFilename,
        file_filter: options.fileFilter,
      }),
    }),
  exportWorkflowToPath: (workflowId: string, path: string) =>
    apiFetch<{ status: string; path: string }>("/api/workflows/export-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ workflow_id: workflowId, path }),
    }),
  // ADR-036 §3.2 — embedded code editor file R/W endpoints.
  getProjectFile: (projectId: string, path: string) =>
    apiFetch<ProjectFileResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
    ),
  putProjectFile: (projectId: string, path: string, content: string, options?: VersionedWriteOptions) => {
    const sourceId = options?.sourceId ?? createClientSourceId("file");
    return apiFetch<ProjectFileWriteResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
      {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ content, source: options?.source ?? "canvas", source_id: sourceId }),
      },
    );
  },
  // ADR-036 §3.12 — block template scaffold endpoint (I36c).
  getBlockTemplate: (kind: string = "basic") =>
    apiFetch<{ kind: string; content: string; suggested_filename: string }>(
      `/api/blocks/template?kind=${encodeURIComponent(kind)}`,
    ),
  // ADR-036 §3.3 — server-side ruff lint endpoint.
  lintPython: (content: string, filename: string) =>
    apiFetch<{
      diagnostics: Array<{
        line: number;
        column: number;
        end_line: number;
        end_column: number;
        code: string;
        severity: string;
        message: string;
      }>;
      note?: string;
    }>("/api/lint/python", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ content, filename }),
    }),

  // ---------------------------------------------------------------------
  // ADR-038 §3.8 — Lineage REST surface (D38-2.4b skeleton).
  //
  // Function bodies throw new Error("TODO: D38-2.4c — ...") so the
  // skeleton compiles + tests can mock these directly while the IMPL
  // agent (D38-2.4c) wires them to real fetch calls.
  //
  // URL shapes match the backend stubs declared by D38-2.4a in
  // `src/scistudio/api/routes/runs.py`. Both PRs target tracking branch
  // `track/adr-038/lineage-db`; if either PR refines a path the other
  // updates here.
  //
  // The namespace pattern (`api.lineage.getRuns(...)`) groups Lineage
  // calls so callers do not collide with `api.list*` / `api.get*` from
  // the existing surface. Mirrors how a future `api.git.*` namespace
  // will land for ADR-039 in D39-2.3a (sibling tracking branch — out of
  // scope here, mentioned only to avoid future merge surprises).
  // ---------------------------------------------------------------------
  lineage: {
    /**
     * GET /api/runs?workflow_id=...&offset=...&limit=...
     *
     * Backend wraps the list in {runs, offset, limit, has_more}; we only
     * surface the runs array to the slice. Pagination is a future
     * polish issue (ADR-038 §7.3 row counts are KB-MB).
     *
     * Backend rows include extra columns the slice/UI does not use
     * (workflow_yaml_snapshot, environment_snapshot, user_notes, etc.).
     * We also compute the convenience fields the frontend type needs
     * (block_count, duration_ms, workflow_dirty as boolean).
     */
    getRuns: async (
      params?: LineageGetRunsParams,
    ): Promise<LineageGetRunsResponse> => {
      const qs = new URLSearchParams();
      if (params?.workflowId !== undefined) {
        qs.set("workflow_id", params.workflowId);
      }
      if (params?.limit !== undefined) {
        qs.set("limit", String(params.limit));
      }
      const path = qs.toString() ? `/api/runs?${qs.toString()}` : "/api/runs";
      const raw = await apiFetch<{ runs: Record<string, unknown>[] }>(path);
      const runs = (raw.runs ?? []).map(adaptRunSummary);
      return { runs };
    },

    /**
     * GET /api/runs/{run_id}
     *
     * Backend returns {run, block_executions} with raw SQLite rows.
     * We parse JSON columns, compute duration_ms / block_count, and
     * surface the frontend's richer LineageRunDetail shape. Block I/O
     * is not joined server-side yet (ADR-038 follow-up) — inputs and
     * outputs default to [] for v1.
     */
    getRun: async (runId: string): Promise<LineageRunDetail> => {
      const raw = await apiFetch<{
        run: Record<string, unknown>;
        block_executions: Record<string, unknown>[];
      }>(`/api/runs/${encodeURIComponent(runId)}`);
      const runSummary = adaptRunSummary(raw.run);
      const blocks = (raw.block_executions ?? []).map(adaptBlockExecution);
      const summaryWithCount: LineageRunSummary = {
        ...runSummary,
        block_count: blocks.length,
      };
      return {
        run: summaryWithCount,
        blocks,
        environment_snapshot: parseJsonObject(raw.run.environment_snapshot),
        workflow_yaml_snapshot:
          (raw.run.workflow_yaml_snapshot as string | null | undefined) ?? null,
      };
    },

    /**
     * GET /api/runs/{run_id}/methods
     *
     * Backend serves the markdown as text/markdown (PlainTextResponse),
     * so we fetch it as text rather than going through apiFetch's JSON
     * decoder.
     */
    getRunMethods: async (runId: string): Promise<LineageMethodsResponse> => {
      const response = await fetch(
        `/api/runs/${encodeURIComponent(runId)}/methods`,
      );
      if (!response.ok) {
        const payload = (await response
          .json()
          .catch(() => ({ detail: response.statusText }))) as {
          detail?: string;
        };
        throw new ApiError(
          payload.detail ?? `Request failed with ${response.status}`,
          response.status,
        );
      }
      const markdown = await response.text();
      return { markdown };
    },

    /**
     * Re-run validation is an ADR-038 §3.6 follow-up; the backend route
     * does not exist as of D38-2.4a. We return an empty-warnings stub so
     * the RerunDialog renders the "no drift detected" clean banner. When
     * the route ships, replace this with a real fetch call.
     */
    validateRerun: async (
      _runId: string,
    ): Promise<LineageRerunValidation> => {
      return { input_warnings: [], env_warnings: [] };
    },

    /**
     * POST /api/runs/{run_id}/rerun
     *
     * Backend returns {rerun_of, workflow_id, execute_from_block_id,
     * result} — the new run_id is not surfaced. RerunDialog refreshes
     * the runs list after a successful rerun; the new row will appear
     * at the top. We return new_run_id="" as a placeholder so callers
     * don't break.
     */
    rerunRun: async (runId: string): Promise<LineageRerunResponse> => {
      await apiFetch<unknown>(`/api/runs/${encodeURIComponent(runId)}/rerun`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({}),
      });
      return { new_run_id: "" };
    },
  },

  // -------------------------------------------------------------------------
  // ADR-039 §3.5 — Git versioning REST surface (D39-2.3a skeleton stubs).
  //
  // These wrap the routes registered by `src/scistudio/api/routes/git.py`
  // (PR #927). They are TYPED but otherwise straight passthroughs — no
  // client-side semantics live here. D39-2.3b consumers (gitSlice, the
  // Git/* components) call these directly and translate the response
  // into store state.
  //
  // Wire contract reference: see `frontend/src/types/api.ts` for the
  // GitCommit / GitBranch / GitStatus / GitMergeResult shapes.
  // -------------------------------------------------------------------------
  gitCommit: (body: { message: string; author?: string; files?: string[] }) =>
    apiFetch<GitCommitResponse>("/api/git/commit", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  gitLog: (params?: { branch?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.branch) search.set("branch", params.branch);
    if (typeof params?.limit === "number") search.set("limit", String(params.limit));
    const qs = search.toString();
    return apiFetch<GitCommit[]>(`/api/git/log${qs ? `?${qs}` : ""}`);
  },
  gitDiff: (params: { from: string; to?: string; file?: string }) => {
    const search = new URLSearchParams();
    search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    if (params.file) search.set("file", params.file);
    return apiFetch<GitDiff>(`/api/git/diff?${search.toString()}`);
  },
  gitRestore: (body: { commit_sha: string; files?: string[] }) =>
    apiFetch<GitRestoreResult>("/api/git/restore", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),

  // Branches
  gitBranches: () => apiFetch<GitBranch[]>("/api/git/branches"),
  gitBranchSwitch: (branch_name: string) =>
    apiFetch<{
      status: string;
      current_branch: string;
      auto_commit_sha: string | null;
    }>("/api/git/branch/switch", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ branch_name }),
    }),
  gitBranchCreate: (body: { name: string; base_sha?: string }) =>
    apiFetch<{ status: string; name: string }>("/api/git/branch/create", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  gitBranchDelete: (name: string, force = false) =>
    apiFetch<{ status: string }>(
      `/api/git/branches/${encodeURIComponent(name)}${force ? "?force=true" : ""}`,
      { method: "DELETE" },
    ),

  // Status
  gitStatus: () => apiFetch<GitStatus>("/api/git/status"),

  // Merge / cherry-pick
  gitMerge: (source_branch: string) =>
    apiFetch<GitMergeResult>("/api/git/merge", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ source_branch }),
    }),
  gitCherryPick: (commit_sha: string) =>
    apiFetch<GitMergeResult>("/api/git/cherry-pick", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ commit_sha }),
    }),

  // Conflict-resolution finalization (consumed by MergeFlow in D39-2.4a)
  gitMergeStageFile: (file: string) =>
    apiFetch<{ status: string }>("/api/git/merge/stage-file", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ file }),
    }),
  gitMergeComplete: () =>
    apiFetch<{ status: string; commit_sha: string }>("/api/git/merge/complete", {
      method: "POST",
      headers: JSON_HEADERS,
    }),
  gitMergeAbort: () =>
    apiFetch<{ status: string }>("/api/git/merge/abort", {
      method: "POST",
      headers: JSON_HEADERS,
    }),
};

// ---------------------------------------------------------------------------
// Lineage response adapters
// ---------------------------------------------------------------------------

/**
 * Backend ``runs`` rows are raw SQLite values: ``workflow_dirty`` is 0/1,
 * ``environment_snapshot`` is a JSON string, ``finished_at`` may be null.
 * Convert to the frontend wire type and compute derived fields.
 */
function adaptRunSummary(row: Record<string, unknown>): LineageRunSummary {
  const startedAt = String(row.started_at ?? "");
  const finishedAt = (row.finished_at as string | null | undefined) ?? null;
  const durationMs = computeDurationMs(startedAt, finishedAt);
  return {
    run_id: String(row.run_id ?? ""),
    workflow_id: String(row.workflow_id ?? ""),
    workflow_git_commit: (row.workflow_git_commit as string | null) ?? null,
    workflow_dirty: Boolean(row.workflow_dirty),
    started_at: startedAt,
    finished_at: finishedAt,
    status: (row.status as LineageRunSummary["status"]) ?? "completed",
    triggered_by:
      (row.triggered_by as LineageRunSummary["triggered_by"]) ?? "user",
    parent_run_id: (row.parent_run_id as string | null) ?? null,
    execute_from_block_id:
      (row.execute_from_block_id as string | null) ?? null,
    // Codex P2 (PR #944): backend's GET /api/runs returns raw runs-table
    // rows and does NOT include a block_count column, so a static `0`
    // default would silently misreport "0 block(s)" for every list row.
    // Surface `null` ("unknown from this endpoint") instead; the detail
    // endpoint backfills the true count when the user selects the run.
    block_count: typeof row.block_count === "number" ? row.block_count : null,
    duration_ms: durationMs,
  };
}

function adaptBlockExecution(
  row: Record<string, unknown>,
): LineageBlockExecution {
  // Hotfix #1015: wire backend-supplied inputs/outputs through. Pre-fix
  // this adapter unconditionally returned `inputs: []` / `outputs: []`
  // with a "future enhancement" comment, but #996 already inlined the
  // join server-side. The Lineage block cards therefore rendered "0
  // inputs / 0 outputs" for every expanded block even though the
  // /api/runs/{id} response carried the data and Methods export
  // surfaced it correctly.
  //
  // Backend entry shape (see `src/scistudio/api/routes/runs.py::get_run`):
  //   { direction, port_name, position, object_id, type_name, backend,
  //     storage_path, produced_by_execution }
  //
  // The frontend type (`LineageDataObjectRef`) only carries the fields
  // the UI consumes; `direction`, `backend`, `produced_by_execution`
  // are dropped at this adapter boundary. The `direction` separator is
  // already applied server-side (inputs vs outputs bucket), so the
  // adapter just trusts the bucket assignment.
  const rawInputs = (row.inputs as Record<string, unknown>[] | undefined) ?? [];
  const rawOutputs =
    (row.outputs as Record<string, unknown>[] | undefined) ?? [];
  return {
    block_execution_id: String(row.block_execution_id ?? ""),
    block_id: String(row.block_id ?? ""),
    block_type: String(row.block_type ?? ""),
    block_version: String(row.block_version ?? "unknown"),
    block_config_resolved: parseJsonRawObject(row.block_config_resolved),
    started_at: String(row.started_at ?? ""),
    finished_at: (row.finished_at as string | null | undefined) ?? null,
    duration_ms:
      typeof row.duration_ms === "number"
        ? row.duration_ms
        : computeDurationMs(
            String(row.started_at ?? ""),
            (row.finished_at as string | null | undefined) ?? null,
          ),
    termination:
      (row.termination as LineageBlockExecution["termination"]) ?? "completed",
    termination_detail:
      (row.termination_detail as string | null | undefined) ?? null,
    inputs: rawInputs.map(adaptDataObjectRef),
    outputs: rawOutputs.map(adaptDataObjectRef),
  };
}

function adaptDataObjectRef(
  row: Record<string, unknown>,
): LineageDataObjectRef {
  return {
    object_id: String(row.object_id ?? ""),
    type_name: String(row.type_name ?? ""),
    port_name: String(row.port_name ?? ""),
    position: typeof row.position === "number" ? row.position : 0,
    storage_path: (row.storage_path as string | null | undefined) ?? null,
  };
}

function parseJsonRawObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "string" || value === "") {
    return {};
  }
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // fall through
  }
  return {};
}

function parseJsonObject(value: unknown): Record<string, string> {
  if (typeof value !== "string" || value === "") {
    return {};
  }
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const result: Record<string, string> = {};
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        result[k] = typeof v === "string" ? v : JSON.stringify(v);
      }
      return result;
    }
  } catch {
    // fall through
  }
  return {};
}

function computeDurationMs(
  startedAt: string,
  finishedAt: string | null,
): number | null {
  if (!finishedAt || !startedAt) return null;
  const start = Date.parse(startedAt);
  const end = Date.parse(finishedAt);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return end - start;
}
