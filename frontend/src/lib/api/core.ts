/**
 * Shared low-level HTTP helpers for the `api.*` surface.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422) so each domain module
 * (projects, workflows, git, lineage, ...) can import the same fetcher
 * without bloating the file past the 500-LOC ceiling.
 *
 * The public `ApiError` symbol is re-exported by `../api.ts` so existing
 * `import { ApiError } from "../lib/api"` callers keep working.
 */

import { logger } from "../logger";

export const JSON_HEADERS = {
  "Content-Type": "application/json",
};

/** Generate a short correlation id matching the backend's X-Request-ID format. */
function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  }
  return Math.random().toString(16).slice(2, 18);
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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // #1741: attach a correlation id (X-Request-ID) and emit DEBUG at the API
  // boundary so every call is traceable across frontend -> backend logs.
  const requestId = newRequestId();
  const headers = new Headers(init?.headers);
  headers.set("X-Request-ID", requestId);
  const method = init?.method ?? "GET";
  const started = typeof performance !== "undefined" ? performance.now() : 0;
  logger.debug(`→ ${method} ${path}`, { request_id: requestId });

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (error) {
    logger.error(`network error: ${method} ${path}`, {
      request_id: requestId,
      error: String(error),
    });
    throw error;
  }
  const elapsedMs = Math.round(
    (typeof performance !== "undefined" ? performance.now() : 0) - started,
  );

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
    // Opaque server errors (a ``{"detail": "Internal Server Error"}`` body or a
    // non-JSON body that fell back to ``statusText``) carry no status code, so
    // append it: "Internal Server Error" -> "Internal Server Error (HTTP 500)".
    if (response.status >= 500 && !message.includes(String(response.status))) {
      message = `${message} (HTTP ${response.status})`;
    }
    logger.warn(`${method} ${path} ${response.status} ${elapsedMs}ms`, { request_id: requestId });
    throw new ApiError(message, response.status);
  }

  logger.debug(`← ${method} ${path} ${response.status} ${elapsedMs}ms`, { request_id: requestId });
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
