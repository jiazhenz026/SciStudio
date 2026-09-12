import type { PreviewTarget } from "../types/api";

/**
 * ADR-054 FR-001 — the three context kinds the backend mints. `miniapp` is
 * the Phase D addition: it is the only kind whose context owns a resident
 * `panel.py` process, and the only one granted the `call` operation.
 */
export type PanelKind = "preview" | "interactive" | "miniapp";

/**
 * ADR-054 FR-015 — the process block the backend attaches to every miniapp
 * context (`PanelProcess.status()`), and the body of
 * `GET /api/panels/contexts/{id}/process`.
 */
export interface PanelProcessStatus {
  state: "starting" | "running" | "unresponsive" | "stopped" | "crashed" | "start_failed";
  pid?: number | null;
  started_at?: number | null;
  /** Resident set size in bytes, or `null` when `psutil` is unavailable. */
  resident_memory?: number | null;
  exit_code?: number | null;
  error?: { type?: string; message?: string } | null;
  /** Present only for `crashed` / `start_failed` (FR-014). */
  log_tail?: string;
}

/** The resident bytes a process block reports, or `null` when it reports none. */
export function residentBytes(process: PanelProcessStatus | null | undefined): number | null {
  return typeof process?.resident_memory === "number" ? process.resident_memory : null;
}

export interface PanelCreateRequest {
  kind: PanelKind;
  panel_id?: string;
  target?: PreviewTarget;
  query?: Record<string, unknown>;
  preview_session_id?: string;
  view_state?: unknown;
  parent_context_id?: string;
  workflow_id?: string;
  block_id?: string;
  /** ADR-054 FR-002 — the block output a `miniapp` context runs on. */
  source?: { workflow_id: string; block_id: string; port: string };
  /**
   * ADR-054 FR-013 — the `/ws` client that opened this context. The backend
   * closes the context (and ends its process) once that client has been
   * disconnected for its grace period.
   */
  ws_client_id?: string;
}
export interface PanelContext {
  context_id: string;
  bootstrap_proof: string;
  panel: { id: string; api_version: string; name?: string };
  kind: PanelKind;
  operations: string[];
  services: string[];
  input: Record<string, unknown>;
  view_state?: unknown;
  token: string;
  expires_at: number;
  entry_url: string;
  sdk_url: string;
  lib_base_url: string;
  /**
   * ADR-054 FR-015 — present (non-null) only for a `miniapp` context whose
   * panel carries `panel.py`. Optional so existing context literals keep
   * compiling.
   */
  process?: PanelProcessStatus | null;
}
export interface PanelTheme {
  mode: "light" | "dark";
  tokens: Record<string, string>;
}
export interface PanelMessage {
  v: number;
  id: string;
  type: string;
  payload: unknown;
}
export interface PanelSnapshot {
  target: PreviewTarget;
  panelId?: string;
  previewSessionId?: string;
  viewState?: unknown;
}
export class PanelError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "PanelError";
  }
}
export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
export function isJsonSafe(value: unknown, seen = new Set<unknown>()): boolean {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || seen.has(value)) return false;
  if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype) return false;
  seen.add(value);
  const valid = Object.values(value).every((item) => isJsonSafe(item, seen));
  seen.delete(value);
  return valid;
}
