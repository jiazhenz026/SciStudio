/**
 * Zustand slice for AI chat state (stub).
 *
 * Owns the per-session event log, current input draft, and pending
 * permission requests. T-ECA-303 fills in the real reducers; this
 * scaffold just defines the slice shape and empty initial state so the
 * store composes cleanly.
 *
 * Pattern mirrors `chatSlice.ts` and `workflowSlice.ts`: a typed
 * `StateCreator` plus an entry in `store/types.ts`'s `AppStore` union.
 * The slice IS NOT wired into `store/index.ts` yet — T-ECA-303 wires it
 * once the reducers exist, to avoid persisting empty defaults during
 * the scaffold phase.
 */

import type { StateCreator } from "zustand";

import type { AgentEvent, PermissionMode } from "../types/agentEvents";

/**
 * Pending permission prompt awaiting a user decision; surfaced by the
 * backend `permission_request` WS message.
 */
export interface PendingPermission {
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
}

export interface AIChatSlice {
  /** Active chat session id, or null if no chat is open. */
  activeChatId: string | null;
  /** Canonical events keyed by chat id. */
  eventsByChat: Record<string, AgentEvent[]>;
  /** Pending permission requests keyed by chat id. */
  pendingPermissions: Record<string, PendingPermission | null>;
  /** Current permission policy mode (UI projection of backend setting). */
  permissionMode: PermissionMode;

  setActiveChatId: (chatId: string | null) => void;
  appendEvent: (chatId: string, event: AgentEvent) => void;
  clearEvents: (chatId: string) => void;
  setPendingPermission: (chatId: string, prompt: PendingPermission | null) => void;
  setPermissionMode: (mode: PermissionMode) => void;
}

/**
 * Slice creator stub.
 *
 * The setter bodies are no-ops; T-ECA-303 replaces them with real
 * reducers. They are typed correctly so that consumers (the new
 * AIChat components) compile against the final API.
 *
 * NOTE: The slice is generic over the host store type so it can be
 * composed with the existing `AppStore` once T-ECA-303 wires it in
 * `store/index.ts` and `store/types.ts`. For now it is exported only;
 * not yet merged into `AppStore`.
 */
export const createAIChatSlice: StateCreator<AIChatSlice, [], [], AIChatSlice> = (
  set,
) => ({
  activeChatId: null,
  eventsByChat: {},
  pendingPermissions: {},
  permissionMode: "strict",

  setActiveChatId: (chatId) => set({ activeChatId: chatId }),
  appendEvent: (chatId, event) =>
    set((state) => ({
      eventsByChat: {
        ...state.eventsByChat,
        [chatId]: [...(state.eventsByChat[chatId] ?? []), event],
      },
    })),
  clearEvents: (chatId) =>
    set((state) => ({
      eventsByChat: { ...state.eventsByChat, [chatId]: [] },
    })),
  setPendingPermission: (chatId, prompt) =>
    set((state) => ({
      pendingPermissions: { ...state.pendingPermissions, [chatId]: prompt },
    })),
  setPermissionMode: (mode) => set({ permissionMode: mode }),
});
