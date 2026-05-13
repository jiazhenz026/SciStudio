/**
 * Sidebar listing known chat sessions for this project.
 *
 * #783: Now fetches persisted session metadata from
 * `GET /api/ai/sessions?project_dir=...` on mount and project change,
 * so chats survive a backend restart. Clicking a session also fetches
 * its transcript and replays historical events into the chat view.
 *
 * Supports: create, rename, delete, switch.
 */

import { useEffect, useState } from "react";

import { useAppStore } from "../../store";
import type { AgentEvent } from "../../types/agentEvents";

interface PersistedSession {
  chat_id: string;
  title: string;
  last_active: string;
  total_turns: number;
}

export function SessionSidebar() {
  const sessions = useAppStore((s) => s.sessions);
  const activeChatId = useAppStore((s) => s.activeChatId);
  const setActiveChatId = useAppStore((s) => s.setActiveChatId);
  const createSession = useAppStore((s) => s.createSession);
  const renameSession = useAppStore((s) => s.renameSession);
  const removeSession = useAppStore((s) => s.removeSession);
  const prependHistoricalEvents = useAppStore((s) => s.prependHistoricalEvents);
  const currentProject = useAppStore((s) => s.currentProject);
  const projectDir = currentProject?.path ?? null;

  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  // #783: fetch persisted sessions on mount / project change so chats
  // survive a backend restart.
  useEffect(() => {
    if (projectDir === null) return;
    let cancelled = false;
    fetch(`/api/ai/sessions?project_dir=${encodeURIComponent(projectDir)}`)
      .then((r) => r.json())
      .then((body) => {
        if (cancelled) return;
        const items: PersistedSession[] = body.sessions ?? [];
        for (const item of items) {
          createSession(item.chat_id, item.title || item.chat_id);
        }
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("SessionSidebar: failed to load sessions", err);
      });
    return () => {
      cancelled = true;
    };
  }, [projectDir, createSession]);

  const handleSwitch = async (id: string) => {
    setActiveChatId(id);
    // #783: replay historical transcript before the WS attaches.
    if (projectDir === null) return;
    try {
      const r = await fetch(
        `/api/ai/sessions/${encodeURIComponent(id)}/transcript?project_dir=${encodeURIComponent(projectDir)}`,
      );
      if (!r.ok) return;
      const text = await r.text();
      const lines = text.split("\n").filter((l) => l.trim());
      const events: AgentEvent[] = lines.map((line) => JSON.parse(line));
      if (events.length > 0) {
        prependHistoricalEvents(id, events);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("SessionSidebar: transcript replay failed", err);
    }
  };

  const handleCreate = () => {
    const id = `chat-${Date.now()}`;
    createSession(id);
    setActiveChatId(id);
  };

  const handleRenameCommit = () => {
    if (renameId !== null && renameDraft.trim()) {
      renameSession(renameId, renameDraft.trim());
    }
    setRenameId(null);
    setRenameDraft("");
  };

  return (
    <div
      data-testid="session-sidebar"
      className="flex h-full w-48 flex-col border-r border-gray-200 bg-gray-50"
    >
      <button
        type="button"
        onClick={handleCreate}
        data-testid="session-new"
        className="m-2 rounded bg-blue-600 px-2 py-1 text-sm text-white hover:bg-blue-700"
      >
        + New chat
      </button>
      <ul className="flex-1 overflow-y-auto px-1">
        {sessions.length === 0 && (
          <li className="px-2 py-1 text-xs italic text-gray-500">No chats yet</li>
        )}
        {sessions.map((s) => {
          const isActive = s.id === activeChatId;
          const isRenaming = renameId === s.id;
          return (
            <li
              key={s.id}
              data-testid={`session-row-${s.id}`}
              className={`flex items-center gap-1 rounded px-2 py-1 text-sm ${
                isActive ? "bg-blue-100" : "hover:bg-gray-100"
              }`}
            >
              {isRenaming ? (
                <input
                  data-testid={`session-rename-input-${s.id}`}
                  className="flex-1 rounded border border-gray-300 px-1 text-sm"
                  value={renameDraft}
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onBlur={handleRenameCommit}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleRenameCommit();
                    } else if (e.key === "Escape") {
                      setRenameId(null);
                      setRenameDraft("");
                    }
                  }}
                  autoFocus
                />
              ) : (
                <button
                  type="button"
                  className="flex-1 truncate text-left"
                  onClick={() => void handleSwitch(s.id)}
                  onDoubleClick={() => {
                    setRenameId(s.id);
                    setRenameDraft(s.title);
                  }}
                >
                  {s.title}
                  {s.ended && (
                    <span className="ml-1 text-xs text-gray-400">(ended)</span>
                  )}
                </button>
              )}
              <button
                type="button"
                data-testid={`session-delete-${s.id}`}
                className="text-xs text-gray-400 hover:text-red-600"
                onClick={() => removeSession(s.id)}
                aria-label={`Delete chat ${s.title}`}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
