/**
 * ADR-054 spec 4 (T-001, T-003) — opening an Explore tab.
 *
 * FR-002 names four entries into the tab and FR-001 says they all land on one:
 * the tab is keyed by the session's notebook path, so a second open of the
 * same notebook activates the tab that exists rather than making a second one.
 *
 * The path is not known before the open, though — `POST /api/explore/sessions`
 * is what decides it, from the block, the file, the run, or the packaged
 * block. So the flow is: send the open, take `notebook_path` off the response,
 * then create or activate `explore:<notebook_path>`. Every caller therefore
 * gets a promise; nothing about the tab is guessed ahead of the answer.
 */

import type { StoreApi } from "zustand";

import { exploreApi } from "../../lib/api/explore";
import type { ExploreOpenSessionRequest, ExploreSessionResponse } from "../../types/api";
import type { ExploreTabMode } from "../../types/ui";
import type { AppStore, ExploreTab, TabState } from "../types";
import { captureActiveTab, dropInactivePreviewTabs } from "./tabHelpers";

type StoreSetter = StoreApi<AppStore>["setState"];
type StoreGetter = StoreApi<AppStore>["getState"];

/** `explore:<notebookPath>` — FR-001's dedup identity. */
export function exploreTabIdFor(notebookPath: string): string {
  return `explore:${notebookPath}`;
}

/** The tab label: the notebook's basename, which is what the person named. */
export function exploreDisplayName(notebookPath: string): string {
  const parts = notebookPath.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || notebookPath;
}

export interface OpenExploreTabOptions {
  /** FR-024 — `"pause"` opens the tab with the notebook pane absent. */
  mode?: ExploreTabMode;
  /** The paused block's node id, in pause mode. */
  pauseNodeId?: string | null;
  /** Override the tab label; defaults to the notebook's basename. */
  displayName?: string;
}

/** Build the tab from a session response. Pure, so the identity rule is testable. */
export function exploreTabFromSession(
  session: ExploreSessionResponse,
  options: OpenExploreTabOptions = {},
): ExploreTab {
  const mode = options.mode ?? "session";
  return {
    kind: "explore",
    id: exploreTabIdFor(session.notebook_path),
    notebookPath: session.notebook_path,
    sessionId: session.session_id,
    displayName: options.displayName ?? exploreDisplayName(session.notebook_path),
    mode,
    boundRunId: session.bound_run?.run_id ?? null,
    pauseNodeId: options.pauseNodeId ?? null,
    // FR-024: a pause tab has no notebook pane until the person asks for one.
    notebookVisible: mode === "session",
    restoring: false,
    openedAt: Date.now(),
  };
}

/**
 * Place an Explore tab in the tab list, activating it either way.
 *
 * Activating rather than replacing when the id already exists is FR-001's
 * "opening a session whose tab exists activates that tab"; the tab's session
 * id is refreshed on the way past so a reopened session is bound to the new
 * one rather than the closed one.
 */
export function placeExploreTab(state: AppStore, tab: ExploreTab): Partial<AppStore> {
  const existing = state.tabs.find((candidate) => candidate.id === tab.id);
  const currentActive = state.tabs.find((candidate) => candidate.id === state.activeTabId) ?? null;
  const captured: TabState[] = currentActive
    ? state.tabs.map((candidate) =>
        candidate.id === state.activeTabId ? captureActiveTab(state, candidate) : candidate,
      )
    : [...state.tabs];

  const tabs = existing
    ? captured.map((candidate) =>
        candidate.id === tab.id
          ? // Keep the pane the person had open; only the session identity and
            // the bound run are news.
            {
              ...tab,
              notebookVisible:
                candidate.kind === "explore" ? candidate.notebookVisible : tab.notebookVisible,
            }
          : candidate,
      )
    : [...captured, tab];

  return {
    // An Explore tab takes focus, which drops any preview tab left behind.
    tabs: dropInactivePreviewTabs(tabs, tab.id),
    activeTabId: tab.id,
  };
}

export function createOpenExploreTab(set: StoreSetter, get: StoreGetter) {
  return async (
    request: ExploreOpenSessionRequest,
    options: OpenExploreTabOptions = {},
  ): Promise<ExploreTab | null> => {
    let session: ExploreSessionResponse;
    try {
      session = await exploreApi.openExploreSession(request);
    } catch (error) {
      // The refusal belongs to whoever asked — the canvas menu, the tree menu,
      // the pause. Nothing is written to the slice, because there is no
      // session and FR-034 leaves no room for a placeholder.
      console.warn("[explore] open session failed", error);
      throw error;
    }
    const state = get();
    state.applyExploreSession(session);
    const tab = exploreTabFromSession(session, options);
    set(placeExploreTab(get(), tab));
    return tab;
  };
}

/**
 * FR-001's other half — re-fetch a rehydrated tab's session state.
 *
 * A persisted tab comes back with its notebook path and no session id, so the
 * restore reopens the notebook (`source: "notebook"`), which is the backend's
 * own way of picking up a notebook the session list reported as closed. The
 * tab keeps its id, so the reload does not move it or duplicate it.
 */
export function createRestoreExploreTab(set: StoreSetter, get: StoreGetter) {
  return async (notebookPath: string): Promise<void> => {
    const state = get();
    state.noteExploreSessionOpening(notebookPath);
    try {
      const session = await exploreApi.openExploreSession({
        source: "notebook",
        path: notebookPath,
      });
      get().applyExploreSession(session);
      set((current) => ({
        tabs: current.tabs.map((tab) =>
          tab.kind === "explore" && tab.notebookPath === notebookPath
            ? { ...tab, sessionId: session.session_id, restoring: false }
            : tab,
        ),
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      get().noteExploreSessionFailed(notebookPath, message);
      set((current) => ({
        tabs: current.tabs.map((tab) =>
          tab.kind === "explore" && tab.notebookPath === notebookPath
            ? { ...tab, restoring: false }
            : tab,
        ),
      }));
    }
  };
}

/** FR-026 — show or hide the notebook pane of a pause tab. */
export function createSetExploreNotebookVisible(set: StoreSetter) {
  return (tabId: string, visible: boolean): void => {
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.kind === "explore" && tab.id === tabId ? { ...tab, notebookVisible: visible } : tab,
      ),
    }));
  };
}
