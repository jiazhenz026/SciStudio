import type { PreviewTarget } from "../types/api";

export type PanelKind = "preview" | "interactive";
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
}
export interface PanelContext {
  context_id: string;
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
  panelId: string;
  viewState?: unknown;
}
export class PanelError extends Error {
  constructor(public code: string, message: string) {
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
