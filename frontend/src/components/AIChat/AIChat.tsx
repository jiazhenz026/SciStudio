/**
 * Top-level AIChat container per ADR-033 §3 D5.1.
 *
 * Layout:
 *   ┌──────────────┬──────────────────────────────────────────┐
 *   │              │ AgentStatusBanner                        │
 *   │              ├──────────────────────────────────────────┤
 *   │ SessionSide- │ ChatMessageList                          │
 *   │ bar          │                                          │
 *   │              ├──────────────────────────────────────────┤
 *   │              │ input bar + send/cancel                  │
 *   └──────────────┴──────────────────────────────────────────┘
 *  + PermissionPrompt modal overlay
 *  + SettingsPanel (collapsed by default)
 *
 * Wires the active chat to `useAgentWebSocket`; the WS hook drives the
 * shared `aiChatSlice` state.
 */

import { useState } from "react";

import { useAgentWebSocket } from "../../hooks/useAgentWebSocket";
import { useAppStore } from "../../store";
import { AgentStatusBanner } from "./AgentStatusBanner";
import { ChatMessageList } from "./ChatMessageList";
import { PermissionPrompt } from "./PermissionPrompt";
import { SessionSidebar } from "./SessionSidebar";
import { SettingsPanel } from "./SettingsPanel";

export function AIChat() {
  const activeChatId = useAppStore((s) => s.activeChatId);
  const currentProject = useAppStore((s) => s.currentProject);
  const sessions = useAppStore((s) => s.sessions);
  const projectDir = currentProject?.path ?? null;

  const activeSession =
    activeChatId !== null ? sessions.find((s) => s.id === activeChatId) ?? null : null;
  const sessionEnded = activeSession?.ended ?? false;

  const { state, sendMessage, cancel, sendPermissionDecision } = useAgentWebSocket(
    activeChatId,
    projectDir,
  );

  const [draft, setDraft] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleSend = () => {
    if (!draft.trim() || !activeChatId) return;
    const ok = sendMessage(draft);
    if (ok) {
      setDraft("");
    }
  };

  return (
    <div data-testid="aichat-root" className="flex h-full w-full">
      <SessionSidebar />
      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 bg-white px-2 py-1">
          <span data-testid="aichat-ws-state" className="text-xs text-gray-500">
            {state}
          </span>
          <button
            type="button"
            data-testid="aichat-settings-toggle"
            className="text-xs text-gray-600 underline"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            {settingsOpen ? "Hide settings" : "Settings"}
          </button>
        </div>
        <AgentStatusBanner />
        {settingsOpen && <SettingsPanel />}
        <div className="flex-1 overflow-hidden">
          {activeChatId !== null ? (
            <ChatMessageList chatId={activeChatId} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-gray-500">
              Select or create a chat to start.
            </div>
          )}
        </div>
        <div className="border-t border-gray-200 bg-gray-50 p-2">
          <div className="flex gap-2">
            <textarea
              data-testid="aichat-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={
                activeChatId === null
                  ? "Pick a chat first"
                  : sessionEnded
                    ? "This chat has ended (read-only)"
                    : "Message the agent..."
              }
              disabled={activeChatId === null || sessionEnded}
              className="flex-1 resize-none rounded border border-gray-300 p-1 text-sm disabled:bg-gray-100"
              rows={2}
            />
            <div className="flex flex-col gap-1">
              <button
                type="button"
                data-testid="aichat-send"
                onClick={handleSend}
                disabled={activeChatId === null || sessionEnded || !draft.trim()}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:bg-gray-300"
              >
                Send
              </button>
              <button
                type="button"
                data-testid="aichat-cancel"
                onClick={cancel}
                disabled={activeChatId === null || sessionEnded}
                className="rounded border px-3 py-1 text-sm hover:bg-gray-100 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
      {activeChatId !== null && (
        <PermissionPrompt chatId={activeChatId} onDecide={sendPermissionDecision} />
      )}
    </div>
  );
}
