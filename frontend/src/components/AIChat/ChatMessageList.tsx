/**
 * Scrollable, auto-scrolling list of agent events for the active chat.
 *
 * Reads `eventsByChat[activeChatId]` from `aiChatSlice` and renders each
 * via `EventRenderer`. No virtualisation yet — Phase 3 happy path is
 * <500 events per session per ADR-033 §3 D5.4. If a chat exceeds that,
 * a future ADR will introduce windowing.
 */

import { useEffect, useRef } from "react";

import { useAppStore } from "../../store";
import type { AgentEvent } from "../../types/agentEvents";
import { EventRenderer } from "./EventRenderer";

// Issue #773 — module-level stable empty array. Zustand's useSyncExternalStore
// requires getSnapshot to return a referentially stable value for unchanged
// state; `?? []` creates a new array literal on every render and triggers
// an infinite-render loop ("getSnapshot should be cached") in React 18.
const EMPTY_EVENTS: ReadonlyArray<AgentEvent> = Object.freeze([]);

export interface ChatMessageListProps {
  chatId: string;
}

export function ChatMessageList({ chatId }: ChatMessageListProps) {
  const events = useAppStore((s) => s.eventsByChat[chatId] ?? EMPTY_EVENTS);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // Scroll to bottom whenever a new event arrives.
  useEffect(() => {
    const el = scrollerRef.current;
    if (el !== null) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div
        data-testid="chat-empty"
        className="flex h-full items-center justify-center text-sm text-gray-500"
      >
        No messages yet. Type below to start the conversation.
      </div>
    );
  }

  return (
    <div
      ref={scrollerRef}
      data-testid="chat-list"
      className="flex h-full flex-col gap-1 overflow-y-auto p-2"
    >
      {events.map((event, idx) => (
        <EventRenderer key={idx} event={event} />
      ))}
    </div>
  );
}
