/**
 * ADR-054 Phase D — the MiniApp HTTP client.
 *
 * The per-context operations (`create` / `call` / `process` / `renew` /
 * `close`) stay on `panelsApi`: they are panel-host operations that a MiniApp
 * shares with previews. What lives here is the MiniApp catalogue and the two
 * agent-session routes, plus promotion to the user library.
 */
import { apiFetch, JSON_HEADERS } from "../lib/api/core";
import { useAppStore } from "../store";
import type { MiniAppSource, MiniAppSummary, MiniAppTarget } from "./types";

/** Body of `POST /api/panels/miniapps` (FR-023 / FR-024). */
export interface MiniAppCreateRequest {
  /** What the user typed, at most 4000 characters. */
  request: string;
  source: MiniAppTarget;
  provider?: string | null;
  permission_mode?: string | null;
  /** Optional display name; the backend names it when this is absent. */
  name?: string | null;
}

export interface MiniAppCreated {
  panel_id: string;
  name: string;
  source: MiniAppTarget;
  /** The agent session the backend started, when it started one. */
  session_tab_id: string | null;
  directory: string;
}

/** Body of `POST /api/panels/miniapps/{panel_id}/convert` (FR-036). */
export interface MiniAppConvertRequest {
  outputs: { name: string; type: string; port: string }[];
  note?: string | null;
  provider?: string | null;
  permission_mode?: string | null;
}

export const miniAppsApi = {
  list: () =>
    apiFetch<{ miniapps: MiniAppSummary[] }>("/api/panels/miniapps", { timeoutMs: 15000 }).then(
      (body) => body.miniapps,
    ),
  sources: (panelId: string) =>
    apiFetch<{ sources: MiniAppSource[] }>(
      `/api/panels/miniapps/${encodeURIComponent(panelId)}/sources`,
      { timeoutMs: 15000 },
    ).then((body) => body.sources),
  create: (body: MiniAppCreateRequest) =>
    apiFetch<MiniAppCreated>("/api/panels/miniapps", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
      // FR-024 probes the agent provider before creating anything, so this can
      // legitimately take a while; it must not be cut short mid-probe.
      timeoutMs: 60000,
    }),
  convert: (panelId: string, body: MiniAppConvertRequest) =>
    apiFetch<{ session_tab_id: string | null }>(
      `/api/panels/miniapps/${encodeURIComponent(panelId)}/convert`,
      { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body), timeoutMs: 60000 },
    ),
  /**
   * FR-032 — promote a project MiniApp to `~/.scistudio/panels/` through the
   * ADR-053 FR-017 directory door. `moved` is false when the project copy
   * could not be removed and the promotion degraded to a copy.
   *
   * The route's body needs the project root the panel directory sits under.
   * The pinned caller signature passes only `overwrite`, so the open project's
   * path is the default and `projectDir` is the override for a caller that
   * knows better.
   */
  promote: (panelId: string, opts: { projectDir?: string; overwrite?: boolean } = {}) => {
    const projectDir = opts.projectDir ?? useAppStore.getState().currentProject?.path;
    if (!projectDir) return Promise.reject(new Error("No project is open"));
    return apiFetch<{ target: string; name: string; path: string; moved: boolean }>(
      `/api/user-library/directory?target=panels&name=${encodeURIComponent(panelId)}`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ project_dir: projectDir, overwrite: opts.overwrite ?? false }),
        timeoutMs: 30000,
      },
    );
  },
};
