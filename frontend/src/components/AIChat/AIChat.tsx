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

import { useEffect, useMemo, useState } from "react";

import { useAgentWebSocket } from "../../hooks/useAgentWebSocket";
import { useAppStore } from "../../store";
import type { AgentEvent } from "../../types/agentEvents";
import { AgentStatusBanner } from "./AgentStatusBanner";
import { ChatMessageList } from "./ChatMessageList";
import { PermissionPrompt } from "./PermissionPrompt";
import { SessionSidebar } from "./SessionSidebar";
import { SettingsPanel } from "./SettingsPanel";

// Issue #782: kinds that count as "real assistant content has arrived" and
// should hide the synthetic in-flight Thinking… indicator. The agent's own
// `thinking` content blocks do NOT count — the indicator is replaced by the
// real thinking row in that case (both look similar; the user sees a
// continuous "agent is reasoning" affordance).
const RESPONSE_KINDS = new Set<string>([
  "assistant_text_delta",
  "tool_use",
  "tool_result",
  "thinking",
  "done",
  "error",
]);

export function AIChat() {
  const activeChatId = useAppStore((s) => s.activeChatId);
  const currentProject = useAppStore((s) => s.currentProject);
  const sessions = useAppStore((s) => s.sessions);
  const appendEvent = useAppStore((s) => s.appendEvent);
  const eventsByChat = useAppStore((s) => s.eventsByChat);
  const toggleToolRowsExpanded = useAppStore((s) => s.toggleToolRowsExpanded);
  const projectDir = currentProject?.path ?? null;

  // Issue #784 Bug 2: global Ctrl+O / Cmd+O hotkey toggles the expansion
  // state of all condensed tool rows on the current chat. Matches Claude
  // Code's own UI hotkey. Preference is persisted in localStorage by the
  // store, so it survives reload.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "o" && e.key !== "O") return;
      // Skip when typing into an input/textarea/contenteditable so the
      // hotkey doesn't fight with users typing the letter "o".
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
      }
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.shiftKey || e.altKey) return;
      e.preventDefault();
      toggleToolRowsExpanded();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleToolRowsExpanded]);

  const activeSession =
    activeChatId !== null ? sessions.find((s) => s.id === activeChatId) ?? null : null;
  const sessionEnded = activeSession?.ended ?? false;

  const { state, sendMessage, cancel, sendPermissionDecision } = useAgentWebSocket(
    activeChatId,
    projectDir,
  );

  const [draft, setDraft] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Issue #782 Bug 2: synthetic Thinking… indicator visible from the
  // moment the user sends a message until the first real agent event
  // arrives. Keyed by chatId so switching chats does not leak state.
  const [awaitingResponse, setAwaitingResponse] = useState<Record<string, number>>({});

  const activeEvents: ReadonlyArray<AgentEvent> = useMemo(() => {
    return activeChatId !== null ? eventsByChat[activeChatId] ?? [] : [];
  }, [activeChatId, eventsByChat]);

  // Clear the synthetic indicator when any real assistant content has
  // arrived AFTER the user's last send. We track the event-list length
  // at send-time and look for any RESPONSE_KINDS event past that point.
  useEffect(() => {
    if (activeChatId === null) return;
    const sinceIdx = awaitingResponse[activeChatId];
    if (sinceIdx === undefined) return;
    for (let i = sinceIdx; i < activeEvents.length; i += 1) {
      const ev = activeEvents[i];
      if (RESPONSE_KINDS.has(String(ev.kind))) {
        setAwaitingResponse((prev) => {
          const next = { ...prev };
          delete next[activeChatId];
          return next;
        });
        return;
      }
    }
  }, [activeChatId, activeEvents, awaitingResponse]);

  const isAwaiting =
    activeChatId !== null && awaitingResponse[activeChatId] !== undefined;

  const handleSend = () => {
    if (!draft.trim() || !activeChatId) return;
    const ok = sendMessage(draft);
    if (ok) {
      // Append a synthetic user_message event so the user's question
      // is visible in the conversation feed (the WS doesn't echo it).
      appendEvent(activeChatId, {
        kind: "user_message",
        raw: { content: draft },
      } as unknown as Parameters<typeof appendEvent>[1]);
      // Mark the chat as awaiting first response; the indicator will
      // show until a RESPONSE_KINDS event arrives past this index.
      // +1 because we just appended the user_message itself.
      const sinceIdx = (eventsByChat[activeChatId]?.length ?? 0) + 1;
      setAwaitingResponse((prev) => ({ ...prev, [activeChatId]: sinceIdx }));
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
            <ChatMessageList chatId={activeChatId} showThinkingIndicator={isAwaiting} />
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
              // Issue #782 Bug 3: bound textarea growth — scroll inside
              // the element past ~8 rows instead of expanding past the
              // chat panel and pushing the Send button off-screen.
              className="flex-1 max-h-[200px] resize-none overflow-y-auto rounded border border-gray-300 p-1 text-sm disabled:bg-gray-100"
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
