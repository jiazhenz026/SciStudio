/** Guarded host operations. Static tokens are never sent as operation credentials. */
import type { PreviewEnvelope } from "../../types/api";
import { readPanelBody } from "../../panels/readBody";
import { materializePanelArtifact } from "../../panels/artifact";
import { ApiError, apiFetch, JSON_HEADERS } from "./core";
import type { PanelContext, PanelCreateRequest, PanelProcessStatus } from "../../panels/types";
import { PanelError } from "../../panels/types";

const contextPath = (id: string) => `/api/panels/contexts/${encodeURIComponent(id)}`;

/**
 * ADR-054 FR-011 — a call result is budgeted at `max_result_bytes()`, 64 MiB
 * by default (`src/scistudio/panels/process_config.py`). Reads are capped far
 * lower (8 MiB, below); reusing the read cap here turned a legitimate 20 MB
 * array into a `size_limit` failure the page could not explain.
 */
const CALL_RESULT_LIMIT = 64 * 1024 * 1024;

/**
 * ADR-054 FR-011 — a `panel.py` function that raises answers HTTP **200**
 * with `{error: {type, message, traceback}}`: the process is alive and the
 * call is not an HTTP failure, so `apiFetch` hands the body back as a
 * success. Turn it into a rejection here, or the SDK's pending promise
 * resolves with an error object the page has no reason to inspect.
 */
function callResult(body: Record<string, unknown>): unknown {
  const failure = body.error;
  if (failure !== undefined && failure !== null) {
    const detail = failure as { type?: unknown; message?: unknown };
    const type = typeof detail.type === "string" ? detail.type : "Error";
    const message = typeof detail.message === "string" ? detail.message : String(failure);
    throw new PanelError("call_failed", `${type}: ${message}`);
  }
  return body.result;
}
/** The result of a questionnaire submit (ADR-054 MiniApp FR-050). */
export interface SubmitAnswersResult {
  saved: boolean;
  path: string | null;
  submitted_at: string | null;
  notified: boolean;
  reason: string | null;
  message: string;
}

/** Questionnaire refusals keep a code the page can branch on. */
const SUBMIT_CODES: Record<number, string> = {
  400: "unsupported",
  409: "no_questionnaire",
  422: "invalid_answers",
};

export const panelsApi = {
  create: (request: PanelCreateRequest) =>
    apiFetch<PanelContext>("/api/panels/contexts", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request),
      timeoutMs: 15000,
    }),
  open: (id: string, ref: string) =>
    apiFetch<PreviewEnvelope>(`${contextPath(id)}/open`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ ref }),
      timeoutMs: 15000,
    }),
  close: (id: string) => apiFetch<void>(contextPath(id), { method: "DELETE", keepalive: true }),
  /** Write a panel save to `path`, which the native save dialog returned. */
  save: (id: string, path: string, content: Blob) =>
    apiFetch<{ saved: boolean; destination: "file"; path: string }>(
      `${contextPath(id)}/save?${new URLSearchParams({ path }).toString()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: content,
      },
    ),
  /** ADR-054 FR-015 — 404 `no_process` for a panel that carries no `panel.py`. */
  processStatus: (id: string, signal?: AbortSignal) =>
    apiFetch<PanelProcessStatus>(`${contextPath(id)}/process`, { timeoutMs: 15000, signal }),
  /** ADR-054 FR-014 — a new process for the same context and target. */
  restartProcess: (id: string) =>
    apiFetch<PanelContext>(`${contextPath(id)}/process/restart`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: "{}",
      timeoutMs: 30000,
    }),
  stopProcess: (id: string) =>
    apiFetch<PanelContext>(`${contextPath(id)}/process/stop`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: "{}",
      timeoutMs: 30000,
    }),
  /**
   * ADR-054 FR-016 — forward one page call to the context's `panel.py`.
   * Three answers share HTTP 200: `{result}`, `{error}` (an author exception,
   * rejected by `callResult`), and a NumPy array as `application/octet-stream`.
   */
  async call(id: string, fn: string, args: Record<string, unknown>, signal?: AbortSignal) {
    const response = await apiFetch<Response>(`${contextPath(id)}/call`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ fn, args }),
      responseType: "response",
      signal,
      // The backend's own call timeout is 60 s (`call_timeout()`); leave the
      // deadline to it rather than aborting a call it is still answering.
      timeoutMs: 90000,
    });
    const contentType = response.headers.get("Content-Type") ?? "";
    if (!contentType.startsWith("application/octet-stream")) {
      return callResult((await response.json()) as Record<string, unknown>);
    }
    return {
      ...JSON.parse(response.headers.get("X-Panel-Metadata") ?? "{}"),
      dtype: response.headers.get("X-Panel-Dtype"),
      shape: JSON.parse(response.headers.get("X-Panel-Shape") ?? "[]"),
      data: await readPanelBody(response, { signal, limit: CALL_RESULT_LIMIT }),
    };
  },
  /**
   * ADR-054 MiniApp FR-050 — save a questionnaire submit to `answers.json` and
   * notify the MiniApp's agent session when it is open.
   */
  async submitAnswers(id: string, answers: Record<string, unknown>) {
    try {
      return await apiFetch<SubmitAnswersResult>(`${contextPath(id)}/answers`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ answers }),
        timeoutMs: 15000,
      });
    } catch (error) {
      if (error instanceof ApiError && SUBMIT_CODES[error.status])
        throw new PanelError(SUBMIT_CODES[error.status], error.message);
      throw error;
    }
  },
  renew: (id: string) =>
    apiFetch<PanelContext>(`${contextPath(id)}/renew`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: "{}",
      timeoutMs: 15000,
    }),
  async read(
    id: string,
    ref: string,
    op: string,
    params: Record<string, unknown>,
    signal?: AbortSignal,
  ) {
    // JSON requests use the shared mutation/auth seam. Binary uses the same
    // guarded route and prefix source, with no static token in its credentials.
    if (params.format !== "binary") {
      const result = await apiFetch<Record<string, unknown>>(`${contextPath(id)}/read`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ ref, op, params }),
        timeoutMs: 30000,
        signal,
      });
      return op === "artifact.file" ? materializePanelArtifact(result, signal) : result;
    }
    const response = await apiFetch<Response>(`${contextPath(id)}/read`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ ref, op, params }),
      responseType: "response",
      signal,
      timeoutMs: 30000,
    });
    if (!response.headers.get("Content-Type")?.startsWith("application/octet-stream")) {
      throw new PanelError("invalid_response", "Expected a binary panel response");
    }
    return {
      ...JSON.parse(response.headers.get("X-Panel-Metadata") ?? "{}"),
      dtype: response.headers.get("X-Panel-Dtype"),
      shape: JSON.parse(response.headers.get("X-Panel-Shape") ?? "[]"),
      data: await readPanelBody(response, { signal, limit: 8 * 1024 * 1024 }),
    };
  },
};
