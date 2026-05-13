/**
 * Stub hook for the agent chat WebSocket connection.
 *
 * T-ECA-303 will implement reconnect-with-backoff, message dispatch
 * into `aiChatSlice`, and `permission_decision` round-trip. The shape
 * returned here is the contract T-ECA-303 must satisfy.
 */

import type { AgentEvent } from "../types/agentEvents";

export interface UseAgentWebSocketResult {
  /** Canonical events received so far on this connection. */
  events: AgentEvent[];
  /** Send a user message to the agent. */
  sendMessage: (content: string) => void;
  /** Cancel the in-flight agent turn. */
  cancel: () => void;
}

export function useAgentWebSocket(_chatId: string): UseAgentWebSocketResult {
  // T-ECA-303 will replace this stub with the real WS lifecycle hook.
  return {
    events: [],
    sendMessage: () => {
      // no-op until T-ECA-303
    },
    cancel: () => {
      // no-op until T-ECA-303
    },
  };
}
