import type { StateCreator } from "zustand";

import type { AiBlockStatus, AppStore, TerminalTab, TerminalTabsSlice } from "./types";

/**
 * Generate a short random tab id without pulling in `nanoid` as a new dep.
 * 8 random hex chars are plenty for distinguishing tabs within a session.
 */
function newTabId(): string {
  const arr = new Uint8Array(4);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(arr);
  } else {
    for (let i = 0; i < arr.length; i += 1) arr[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(arr)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Compute the next default title ("Chat N") given existing tabs. */
function nextDefaultTitle(tabs: TerminalTab[]): string {
  // Find highest "Chat N" number already used; use N+1 for the new tab.
  let max = 0;
  for (const t of tabs) {
    const m = /^Chat (\d+)$/.exec(t.title);
    if (m) {
      const n = parseInt(m[1], 10);
      if (!Number.isNaN(n) && n > max) max = n;
    }
  }
  return `Chat ${max + 1}`;
}

/** Compute the next default title ("Terminal N") given existing tabs. */
function nextDefaultUserTerminalTitle(tabs: TerminalTab[]): string {
  let max = 0;
  for (const t of tabs) {
    const m = /^Terminal (\d+)$/.exec(t.title);
    if (m) {
      const n = parseInt(m[1], 10);
      if (!Number.isNaN(n) && n > max) max = n;
    }
  }
  return `Terminal ${max + 1}`;
}

export const createTerminalTabsSlice: StateCreator<AppStore, [], [], TerminalTabsSlice> = (
  set,
) => ({
  terminalTabs: [],
  activeTerminalTabId: null,

  addTerminalTab: () => {
    const id = newTabId();
    set((state) => {
      const title = nextDefaultTitle(state.terminalTabs);
      const tab: TerminalTab = {
        id,
        title,
        provider: null,
        permissionMode: null,
        state: "setup",
      };
      return {
        terminalTabs: [...state.terminalTabs, tab],
        activeTerminalTabId: id,
      };
    });
    return id;
  },

  addUserTerminalTab: () => {
    const id = newTabId();
    set((state) => {
      const title = nextDefaultUserTerminalTitle(state.terminalTabs);
      const tab: TerminalTab = {
        id,
        title,
        provider: "user-terminal",
        permissionMode: "safe",
        state: "running",
        source: "user",
      };
      return {
        terminalTabs: [...state.terminalTabs, tab],
        activeTerminalTabId: id,
      };
    });
    return id;
  },

  closeTerminalTab: (id) =>
    set((state) => {
      const idx = state.terminalTabs.findIndex((t) => t.id === id);
      if (idx === -1) return state;
      const next = state.terminalTabs.filter((t) => t.id !== id);
      let activeId = state.activeTerminalTabId;
      if (activeId === id) {
        // Activate neighbour (prefer the previous tab, fall back to next).
        if (next.length === 0) {
          activeId = null;
        } else if (idx > 0) {
          activeId = next[Math.min(idx - 1, next.length - 1)].id;
        } else {
          activeId = next[0].id;
        }
      }
      return { terminalTabs: next, activeTerminalTabId: activeId };
    }),

  renameTerminalTab: (id, title) =>
    set((state) => ({
      terminalTabs: state.terminalTabs.map((t) => (t.id === id ? { ...t, title } : t)),
    })),

  launchTerminalTab: (id, provider, permissionMode) =>
    set((state) => ({
      terminalTabs: state.terminalTabs.map((t) =>
        t.id === id
          ? {
              ...t,
              provider,
              permissionMode,
              state: "running",
              exitCode: undefined,
              errorMessage: undefined,
            }
          : t,
      ),
    })),

  markTerminalTabExited: (id, code) =>
    set((state) => ({
      terminalTabs: state.terminalTabs.map((t) =>
        t.id === id ? { ...t, state: "closed", exitCode: code } : t,
      ),
    })),

  markTerminalTabErrored: (id, message) =>
    set((state) => ({
      terminalTabs: state.terminalTabs.map((t) =>
        t.id === id ? { ...t, state: "closed", exitCode: -2, errorMessage: message } : t,
      ),
    })),

  reopenTerminalTab: (id) =>
    set((state) => ({
      terminalTabs: state.terminalTabs.map((t) =>
        t.id === id
          ? {
              ...t,
              state: t.provider === "user-terminal" ? "running" : "setup",
              exitCode: undefined,
              errorMessage: undefined,
            }
          : t,
      ),
    })),

  setActiveTerminalTab: (id) => set({ activeTerminalTabId: id }),

  // ADR-035 §3.10 — engine-initiated AI Block tab.
  // The engine has already spawned the PTY before sending block_pty_opened,
  // so we skip the SetupScreen and go straight to "running".
  addAiBlockTerminalTab: ({ tabId, title, blockRunId, permissionMode }) =>
    set((state) => {
      const existing = state.terminalTabs.findIndex((t) => t.id === tabId);
      const tab: TerminalTab = {
        id: tabId,
        title,
        provider: "claude-code", // engine spawns claude (codex equivalent in I35b)
        permissionMode,
        state: "running",
        source: "ai-block",
        blockRunId,
        blockStatus: "paused",
      };
      if (existing >= 0) {
        // Idempotent: replace the entry. Belt-and-braces in case the engine
        // ever resends the open event (e.g. on reconnect).
        const next = state.terminalTabs.slice();
        next[existing] = { ...next[existing], ...tab };
        return { terminalTabs: next, activeTerminalTabId: tabId };
      }
      return {
        terminalTabs: [...state.terminalTabs, tab],
        activeTerminalTabId: tabId,
      };
    }),

  updateAiBlockStatus: (id: string, status: AiBlockStatus) =>
    set((state) => {
      const idx = state.terminalTabs.findIndex((t) => t.id === id);
      if (idx === -1) return state;
      const next = state.terminalTabs.slice();
      next[idx] = { ...next[idx], blockStatus: status };
      return { terminalTabs: next };
    }),

  // Test helper / rehydration hook — replace the whole slice atomically.
  _replaceTerminalTabs: (tabs, activeId) =>
    set({ terminalTabs: tabs, activeTerminalTabId: activeId }),
});

/**
 * Rehydration helper: any tab that was `running` when the page unloaded is
 * dead now (the WebSocket and its PTY did not survive). Downgrade them to
 * `closed` with synthetic exit code `-1` so the user sees the Reopen button.
 *
 * Exported separately from the slice so `store/index.ts` can call it from
 * `onRehydrateStorage`.
 */
export function rehydrateTerminalTabs(tabs: TerminalTab[]): TerminalTab[] {
  return tabs.map((t) => {
    if (t.state !== "running") return t;
    // PTY didn't survive page unload. AI-Block tabs additionally get their
    // blockStatus downgraded to "cancelled" — the workflow run is gone too.
    return {
      ...t,
      state: "closed" as const,
      exitCode: -1,
      errorMessage: undefined,
      ...(t.source === "ai-block" ? { blockStatus: "cancelled" as const } : {}),
    };
  });
}

// Re-export for convenience.
export type { TerminalTab, TerminalTabsSlice };

// Re-export internal helper for tests.
export { newTabId, nextDefaultTitle, nextDefaultUserTerminalTitle };
