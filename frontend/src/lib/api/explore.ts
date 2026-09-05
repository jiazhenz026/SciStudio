/**
 * ADR-054 spec 4 (T-001) — the Explore Session API client.
 *
 * One thin function per route in `src/scistudio/api/routes/explore.py`. The
 * project is implicit: every route resolves the session service from the
 * runtime's active project, so no project id appears in a path here.
 *
 * Nothing in this module holds state. FR-034 makes the store slice the only
 * place a session's truth lives, and it is written from these responses and
 * from the WebSocket events — never from an optimistic guess made at the call
 * site. FR-035: there is no kernel connection here, and there must never be
 * one; every execution goes through `runCell` and comes back as an event.
 */

import type {
  ExploreBindingsResponse,
  ExploreCellsResponse,
  ExploreCloseSessionResponse,
  ExploreCommitResponse,
  ExploreEmitSnippetRequest,
  ExploreEmitSnippetResponse,
  ExploreGraphResponse,
  ExploreKernelListResponse,
  ExploreKernelStateResponse,
  ExploreMarksResponse,
  ExploreOpenSessionRequest,
  ExplorePackageRequest,
  ExplorePackageResponse,
  ExplorePackagingCheckRequest,
  ExplorePackagingCheckResponse,
  ExploreRunResponse,
  ExploreSessionListResponse,
  ExploreSessionResponse,
  ExploreWindowRequest,
  ExploreWindowResponse,
} from "../../types/api";
import { JSON_HEADERS, apiFetch } from "./core";

const ROOT = "/api/explore";

function encodeSegment(value: string): string {
  return encodeURIComponent(value);
}

export const exploreApi = {
  /** `POST /api/explore/sessions` — open over a block, a file, a paused run, a notebook, or a packaged block. */
  openExploreSession(payload: ExploreOpenSessionRequest): Promise<ExploreSessionResponse> {
    return apiFetch<ExploreSessionResponse>(`${ROOT}/sessions`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  },

  /** `GET /api/explore/sessions` — every notebook in the project's explore directory. */
  listExploreSessions(): Promise<ExploreSessionListResponse> {
    return apiFetch<ExploreSessionListResponse>(`${ROOT}/sessions`);
  },

  /** `GET /api/explore/sessions/{id}` — FR-001's re-fetch on restore. */
  getExploreSession(sessionId: string): Promise<ExploreSessionResponse> {
    return apiFetch<ExploreSessionResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}`);
  },

  /** `DELETE /api/explore/sessions/{id}` — end the session, with one branch commit. */
  closeExploreSession(sessionId: string, commit = true): Promise<ExploreCloseSessionResponse> {
    return apiFetch<ExploreCloseSessionResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}?commit=${commit ? "true" : "false"}`,
      { method: "DELETE" },
    );
  },

  /** `POST /api/explore/sessions/{id}/commit` — write the branch commit (FR-014). */
  commitExploreSession(sessionId: string, message?: string): Promise<ExploreCommitResponse> {
    return apiFetch<ExploreCommitResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/commit`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ message: message ?? null }),
    });
  },

  /** `GET /api/explore/sessions/{id}/cells`. */
  readExploreCells(sessionId: string): Promise<ExploreCellsResponse> {
    return apiFetch<ExploreCellsResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/cells`);
  },

  /** `PUT /api/explore/sessions/{id}/cells/{cellId}` — replace one cell's source. */
  writeExploreCell(
    sessionId: string,
    cellId: string,
    source: string,
  ): Promise<ExploreCellsResponse> {
    return apiFetch<ExploreCellsResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/cells/${encodeSegment(cellId)}`,
      { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ source }) },
    );
  },

  /** `POST /api/explore/sessions/{id}/cells` — insert after `after`, or at the end. */
  insertExploreCell(
    sessionId: string,
    source = "",
    after?: string | null,
  ): Promise<ExploreCellsResponse> {
    return apiFetch<ExploreCellsResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/cells`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ source, after: after ?? null }),
    });
  },

  /** `PUT /api/explore/sessions/{id}/cells/{cellId}/enabled`. */
  setExploreCellEnabled(
    sessionId: string,
    cellId: string,
    enabled: boolean,
  ): Promise<ExploreCellsResponse> {
    return apiFetch<ExploreCellsResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/cells/${encodeSegment(cellId)}/enabled`,
      { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ enabled }) },
    );
  },

  /** `POST /api/explore/sessions/{id}/cells/{cellId}/run`. */
  runExploreCell(sessionId: string, cellId: string): Promise<ExploreRunResponse> {
    return apiFetch<ExploreRunResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/cells/${encodeSegment(cellId)}/run`,
      { method: "POST" },
    );
  },

  /** `POST /api/explore/sessions/{id}/run-stale` — FR-013's toolbar control. */
  runExploreStale(sessionId: string): Promise<ExploreRunResponse> {
    return apiFetch<ExploreRunResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/run-stale`, {
      method: "POST",
    });
  },

  /** `POST /api/explore/sessions/{id}/cells/{cellId}/run-with-upstream` — FR-013's cell control. */
  runExploreWithUpstream(sessionId: string, cellId: string): Promise<ExploreRunResponse> {
    return apiFetch<ExploreRunResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/cells/${encodeSegment(cellId)}/run-with-upstream`,
      { method: "POST" },
    );
  },

  /** `POST /api/explore/sessions/{id}/interrupt`. */
  interruptExploreSession(sessionId: string): Promise<ExploreKernelStateResponse> {
    return apiFetch<ExploreKernelStateResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/interrupt`,
      { method: "POST" },
    );
  },

  /** `POST /api/explore/sessions/{id}/restart`. */
  restartExploreSession(sessionId: string): Promise<ExploreKernelStateResponse> {
    return apiFetch<ExploreKernelStateResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/restart`,
      { method: "POST" },
    );
  },

  /** `GET /api/explore/sessions/{id}/graph` — FR-032's source. */
  getExploreGraph(sessionId: string): Promise<ExploreGraphResponse> {
    return apiFetch<ExploreGraphResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/graph`);
  },

  /** `GET /api/explore/sessions/{id}/marks` — FR-012's source; never computed here. */
  getExploreMarks(sessionId: string): Promise<ExploreMarksResponse> {
    return apiFetch<ExploreMarksResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/marks`);
  },

  /** `GET /api/explore/sessions/{id}/bindings` — FR-018's source; never computed here. */
  getExploreBindings(sessionId: string): Promise<ExploreBindingsResponse> {
    return apiFetch<ExploreBindingsResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/bindings`,
    );
  },

  /** `POST /api/explore/sessions/{id}/window` — a windowed read of one variable. */
  windowExploreVariable(
    sessionId: string,
    payload: ExploreWindowRequest,
  ): Promise<ExploreWindowResponse> {
    return apiFetch<ExploreWindowResponse>(`${ROOT}/sessions/${encodeSegment(sessionId)}/window`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  },

  /** `POST /api/explore/sessions/{id}/snippets` — FR-021's emission. */
  emitExploreSnippet(
    sessionId: string,
    payload: ExploreEmitSnippetRequest,
  ): Promise<ExploreEmitSnippetResponse> {
    return apiFetch<ExploreEmitSnippetResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/snippets`,
      { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) },
    );
  },

  /** `GET /api/explore/kernels` — FR-015's list. */
  listExploreKernels(): Promise<ExploreKernelListResponse> {
    return apiFetch<ExploreKernelListResponse>(`${ROOT}/kernels`);
  },

  /** `DELETE /api/explore/kernels/{id}` — FR-015's end control. */
  endExploreKernel(sessionId: string): Promise<ExploreKernelStateResponse> {
    return apiFetch<ExploreKernelStateResponse>(`${ROOT}/kernels/${encodeSegment(sessionId)}`, {
      method: "DELETE",
    });
  },

  /** `POST /api/explore/sessions/{id}/packaging/check` — FR-028's report, writing nothing. */
  checkExplorePackaging(
    sessionId: string,
    payload: ExplorePackagingCheckRequest = {},
  ): Promise<ExplorePackagingCheckResponse> {
    return apiFetch<ExplorePackagingCheckResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/packaging/check`,
      { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) },
    );
  },

  /** `POST /api/explore/sessions/{id}/package` — FR-028's confirm. */
  packageExploreSession(
    sessionId: string,
    payload: ExplorePackageRequest,
  ): Promise<ExplorePackageResponse> {
    return apiFetch<ExplorePackageResponse>(
      `${ROOT}/sessions/${encodeSegment(sessionId)}/package`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(payload),
      },
    );
  },
};
