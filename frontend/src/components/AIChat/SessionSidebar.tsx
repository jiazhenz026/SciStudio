/**
 * Sidebar listing known chat sessions for this project.
 *
 * NOTE on data source: the backend does not yet expose
 * `GET /api/projects/{id}/sessions` — that endpoint is deferred to
 * Phase 3 follow-up. For now the sidebar lists sessions tracked
 * in-memory in `aiChatSlice` (chats that have received at least one
 * event since the page loaded). This is documented in issue #741.
 *
 * Supports: create, rename, delete, switch.
 */

import { useState } from "react";

import { useAppStore } from "../../store";

export function SessionSidebar() {
  const sessions = useAppStore((s) => s.sessions);
  const activeChatId = useAppStore((s) => s.activeChatId);
  const setActiveChatId = useAppStore((s) => s.setActiveChatId);
  const createSession = useAppStore((s) => s.createSession);
  const renameSession = useAppStore((s) => s.renameSession);
  const removeSession = useAppStore((s) => s.removeSession);

  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

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
                  onClick={() => setActiveChatId(s.id)}
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
