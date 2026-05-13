/**
 * Zustand slice for AI chat state.
 *
 * Owns per-session event log, current pending permission prompt, and
 * sidebar session metadata. Mirrors the protocol envelopes defined in
 * `scieasy.api.schemas`:
 *  - `AgentEventEnvelope`   → appendEvent
 *  - `PermissionRequestEnvelope` → setPendingPermission
 *  - `SessionEndedEnvelope` → markSessionEnded
 *  - `ErrorEnvelope`        → appendEvent (synthetic "error" kind)
 *
 * Composed into the central store via `store/index.ts`.
 */

import type { StateCreator } from "zustand";

import type { AgentEvent, PermissionMode } from "../types/agentEvents";
import type { AppStore } from "./types";

/**
 * Pending permission prompt awaiting a user decision; surfaced by the
 * backend `permission_request` WS message.
 */
export interface PendingPermission {
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
}

/**
 * Lightweight session record for the sidebar.
 *
 * NOTE: Session persistence across reloads is a Phase-3 future task —
 * for now the sidebar lists chats that have received at least one event
 * in the current page load. Issue #741 documents the gap (no backend
 * `GET /api/projects/{id}/sessions` endpoint yet — deferred per the
 * playbook discipline rules).
 */
export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  /** True if the session has ended (won't accept new user messages). */
  ended: boolean;
}

export interface AIChatSlice {
  /** Active chat session id, or null if no chat is open. */
  activeChatId: string | null;
  /** Known chat sessions for the sidebar. */
  sessions: ChatSession[];
  /** Canonical events keyed by chat id. */
  eventsByChat: Record<string, AgentEvent[]>;
  /** Pending permission requests keyed by chat id. */
  pendingPermissions: Record<string, PendingPermission | null>;
  /** Current permission policy mode (UI projection of backend setting). */
  permissionMode: PermissionMode;
  /** User-visible provider selection ("claude-code" | "codex"). */
  providerName: string;
  /** Per-tool always-allow flags, keyed by tool name. */
  alwaysAllowedTools: Record<string, boolean>;

  setActiveChatId: (chatId: string | null) => void;
  appendEvent: (chatId: string, event: AgentEvent) => void;
  /**
   * Replace the chat's event list with historical events (#783).
   * Used by the sessions sidebar when opening a prior chat — the
   * transcript replay endpoint streams every recorded event and we
   * prepend them so the user sees the full history before the live
   * WS attaches.
   */
  prependHistoricalEvents: (chatId: string, events: AgentEvent[]) => void;
  clearEvents: (chatId: string) => void;
  setPendingPermission: (chatId: string, prompt: PendingPermission | null) => void;
  setPermissionMode: (mode: PermissionMode) => void;
  setProviderName: (name: string) => void;
  markAlwaysAllowed: (toolName: string) => void;
  createSession: (id: string, title?: string) => void;
  renameSession: (id: string, title: string) => void;
  removeSession: (id: string) => void;
  markSessionEnded: (id: string) => void;
}

export const createAIChatSlice: StateCreator<AppStore, [], [], AIChatSlice> = (set) => ({
  activeChatId: null,
  sessions: [],
  eventsByChat: {},
  pendingPermissions: {},
  permissionMode: "strict",
  providerName: "claude-code",
  alwaysAllowedTools: {},

  setActiveChatId: (chatId) => set({ activeChatId: chatId }),

  appendEvent: (chatId, event) =>
    set((state) => {
      // Auto-register a session the first time an event arrives for it.
      const sessions =
        state.sessions.find((s) => s.id === chatId) !== undefined
          ? state.sessions
          : [
              ...state.sessions,
              {
                id: chatId,
                title: chatId,
                createdAt: Date.now(),
                ended: false,
              },
            ];
      return {
        sessions,
        eventsByChat: {
          ...state.eventsByChat,
          [chatId]: [...(state.eventsByChat[chatId] ?? []), event],
        },
      };
    }),

  prependHistoricalEvents: (chatId, events) =>
    set((state) => {
      const existing = state.eventsByChat[chatId] ?? [];
      // Idempotent: if the buffer already starts with the same history
      // (same length), don't re-prepend.
      if (existing.length >= events.length) {
        return {} as Partial<AppStore>;
      }
      return {
        eventsByChat: {
          ...state.eventsByChat,
          [chatId]: [...events, ...existing],
        },
      };
    }),

  clearEvents: (chatId) =>
    set((state) => ({
      eventsByChat: { ...state.eventsByChat, [chatId]: [] },
    })),

  setPendingPermission: (chatId, prompt) =>
    set((state) => ({
      pendingPermissions: { ...state.pendingPermissions, [chatId]: prompt },
    })),

  setPermissionMode: (mode) => set({ permissionMode: mode }),
  setProviderName: (providerName) => set({ providerName }),
  markAlwaysAllowed: (toolName) =>
    set((state) => ({
      alwaysAllowedTools: { ...state.alwaysAllowedTools, [toolName]: true },
    })),

  createSession: (id, title) =>
    set((state) => {
      if (state.sessions.find((s) => s.id === id) !== undefined) {
        return {} as Partial<AppStore>;
      }
      return {
        sessions: [
          ...state.sessions,
          {
            id,
            title: title ?? id,
            createdAt: Date.now(),
            ended: false,
          },
        ],
      };
    }),

  renameSession: (id, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, title } : s)),
    })),

  removeSession: (id) =>
    set((state) => {
      const restEvents = { ...state.eventsByChat };
      delete restEvents[id];
      const restPerm = { ...state.pendingPermissions };
      delete restPerm[id];
      return {
        sessions: state.sessions.filter((s) => s.id !== id),
        eventsByChat: restEvents,
        pendingPermissions: restPerm,
        activeChatId: state.activeChatId === id ? null : state.activeChatId,
      };
    }),

  markSessionEnded: (id) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, ended: true } : s)),
    })),
});
