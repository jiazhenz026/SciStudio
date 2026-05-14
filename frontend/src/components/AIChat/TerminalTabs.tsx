/**
 * ADR-034 Phase 1.3: TerminalTabs — multi-tab terminal container.
 *
 * Renders a tab strip across the top (with rename + close per tab and a `+`
 * button to add) and the active tab's content below. Window-level keyboard
 * listener handles Ctrl+T (new), Ctrl+W (close), Ctrl+1..9 (switch). Uses
 * capture phase to win against browser default tab shortcuts.
 *
 * Auto-creates a single setup tab when the panel mounts with zero tabs so
 * the user always sees the SetupScreen without having to click `+`.
 *
 * ADR-035 §3.10 skeleton extension:
 *   - The component (via the `useWebSocket` hook) handles engine-initiated
 *     `block_pty_opened` / `block_pty_closed` events: a new tab type with
 *     `source === "ai-block"` is auto-created and focused. The tab joins
 *     the existing user-launched WS route (the engine has pre-spawned the
 *     PTY; the WS handshake reuses it by tab_id).
 *   - See `handleBlockPtyOpened` / `handleBlockPtyClosed` stubs below.
 */
import { useCallback, useEffect, useState } from "react";

import { sendWebSocketMessage } from "../../hooks/useWebSocket";
import { useAppStore } from "../../store";
import { AiBlockStatusBadge, TerminalTab } from "./TerminalTab";

// Re-export so existing imports / tests continue to work; canonical home is
// blockPtyHandlers.ts (broken out to avoid the cycle with useWebSocket).
export { handleBlockPtyClosed, handleBlockPtyOpened } from "./blockPtyHandlers";

function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      data-testid="terminal-confirm-dialog"
    >
      <div className="w-80 rounded-2xl bg-white p-4 shadow-lg">
        <p className="mb-4 text-sm text-stone-700">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-full border border-stone-300 px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-50"
            onClick={onCancel}
            data-testid="terminal-confirm-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-full bg-red-500 px-3 py-1.5 text-sm text-white hover:bg-red-600"
            onClick={onConfirm}
            data-testid="terminal-confirm-ok"
          >
            Close anyway
          </button>
        </div>
      </div>
    </div>
  );
}

export function TerminalTabs() {
  const tabs = useAppStore((s) => s.terminalTabs);
  const activeTabId = useAppStore((s) => s.activeTerminalTabId);
  const addTerminalTab = useAppStore((s) => s.addTerminalTab);
  const closeTerminalTab = useAppStore((s) => s.closeTerminalTab);
  const renameTerminalTab = useAppStore((s) => s.renameTerminalTab);
  const setActiveTerminalTab = useAppStore((s) => s.setActiveTerminalTab);

  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [pendingClose, setPendingClose] = useState<string | null>(null);

  // Auto-create a tab on first mount when none exist. Effect-driven so it
  // never runs in the reducer (which would break SSR / Vitest).
  useEffect(() => {
    if (tabs.length === 0) {
      addTerminalTab();
    }
    // intentional one-shot
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const requestCloseTab = useCallback(
    (id: string) => {
      const t = tabs.find((tab) => tab.id === id);
      if (t && t.state === "running") {
        setPendingClose(id);
      } else {
        closeTerminalTab(id);
      }
    },
    [closeTerminalTab, tabs],
  );

  // Keyboard shortcuts (window-level, capture phase so Ctrl+W beats Chrome).
  useEffect(() => {
    const handler = (ev: KeyboardEvent) => {
      const ctrl = ev.ctrlKey || ev.metaKey;
      if (!ctrl) return;
      const key = ev.key.toLowerCase();
      if (key === "t" && !ev.shiftKey) {
        ev.preventDefault();
        ev.stopPropagation();
        addTerminalTab();
        return;
      }
      if (key === "w" && !ev.shiftKey) {
        ev.preventDefault();
        ev.stopPropagation();
        if (activeTabId) requestCloseTab(activeTabId);
        return;
      }
      // Ctrl+1..Ctrl+9 -> switch to N-th tab (1-indexed in the UI).
      if (/^[1-9]$/.test(ev.key)) {
        const idx = parseInt(ev.key, 10) - 1;
        if (idx < tabs.length) {
          ev.preventDefault();
          ev.stopPropagation();
          setActiveTerminalTab(tabs[idx].id);
        }
      }
    };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [activeTabId, addTerminalTab, requestCloseTab, setActiveTerminalTab, tabs]);

  const commitRename = useCallback(() => {
    if (renamingId && renameDraft.trim().length > 0) {
      renameTerminalTab(renamingId, renameDraft.trim());
    }
    setRenamingId(null);
    setRenameDraft("");
  }, [renameDraft, renamingId, renameTerminalTab]);

  return (
    <div className="flex h-full flex-col" data-testid="terminal-tabs">
      <div
        className="flex shrink-0 items-center gap-1 border-b border-stone-200 bg-stone-50/60 px-2 py-1"
        role="tablist"
        data-testid="terminal-tabs-strip"
      >
        {tabs.map((tab) => {
          const active = tab.id === activeTabId;
          const isRenaming = renamingId === tab.id;
          return (
            <div
              key={tab.id}
              className={`flex items-center gap-1 rounded-t-md px-2 py-1 text-xs ${
                active
                  ? "bg-white text-ink shadow-sm"
                  : "text-stone-500 hover:text-stone-700"
              }`}
              role="tab"
              aria-selected={active}
              data-testid={`terminal-tab-${tab.id}`}
            >
              {isRenaming ? (
                <input
                  className="w-24 rounded border border-stone-300 px-1 py-0 text-xs"
                  value={renameDraft}
                  autoFocus
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    else if (e.key === "Escape") {
                      setRenamingId(null);
                      setRenameDraft("");
                    }
                  }}
                  data-testid={`terminal-tab-rename-input-${tab.id}`}
                />
              ) : (
                <button
                  type="button"
                  className="select-none"
                  onClick={() => setActiveTerminalTab(tab.id)}
                  onDoubleClick={() => {
                    setRenamingId(tab.id);
                    setRenameDraft(tab.title);
                  }}
                  data-testid={`terminal-tab-title-${tab.id}`}
                >
                  {tab.title}
                  {/* ADR-035 §3.9 — AI-Block status decoration on the tab strip. */}
                  <AiBlockStatusBadge tabId={tab.id} />
                  {tab.state === "running" && tab.source !== "ai-block" ? (
                    <span
                      className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
                      aria-hidden
                    />
                  ) : null}
                </button>
              )}
              <button
                type="button"
                className="ml-1 rounded p-0.5 text-stone-400 hover:bg-stone-200 hover:text-stone-700"
                onClick={(e) => {
                  e.stopPropagation();
                  requestCloseTab(tab.id);
                }}
                aria-label={`Close ${tab.title}`}
                data-testid={`terminal-tab-close-btn-${tab.id}`}
              >
                ×
              </button>
            </div>
          );
        })}
        <button
          type="button"
          className="ml-1 rounded p-1 text-stone-500 hover:bg-stone-200 hover:text-stone-700"
          onClick={() => addTerminalTab()}
          aria-label="New chat tab"
          data-testid="terminal-tabs-add"
        >
          +
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {/* Render every tab and hide non-active ones via CSS. Conditional
            rendering would unmount the inactive TerminalTab whenever the
            user switches tabs, which tears down the WS and kills the PTY
            subprocess — every tab switch would lose the conversation. */}
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`h-full ${tab.id === activeTabId ? "" : "hidden"}`}
            data-testid={`terminal-tab-host-${tab.id}`}
          >
            <TerminalTab tabId={tab.id} />
          </div>
        ))}
        {tabs.length === 0 || !activeTabId ? (
          <div className="flex h-full items-center justify-center text-sm text-stone-400">
            No active tab. Press <kbd className="mx-1 rounded bg-stone-200 px-1">Ctrl</kbd>
            +<kbd className="mx-1 rounded bg-stone-200 px-1">T</kbd> to open one.
          </div>
        ) : null}
      </div>

      {pendingClose
        ? (() => {
            const closingTab = tabs.find((t) => t.id === pendingClose);
            const isAiBlock = closingTab?.source === "ai-block";
            return (
              <ConfirmDialog
                message={
                  isAiBlock
                    ? "This AI Block is still running. Closing will cancel the block run."
                    : "This terminal is still running. Closing will kill its subprocess."
                }
                onConfirm={() => {
                  // ADR-035 §3.9 — user-close-while-running emits cancel so the
                  // engine can transition the block to CANCELLED and tear the
                  // PTY down cleanly rather than leaking the process.
                  if (isAiBlock && closingTab?.blockRunId) {
                    sendWebSocketMessage({
                      type: "block_user_cancel",
                      block_run_id: closingTab.blockRunId,
                      tab_id: closingTab.id,
                    });
                  }
                  closeTerminalTab(pendingClose);
                  setPendingClose(null);
                }}
                onCancel={() => setPendingClose(null)}
              />
            );
          })()
        : null}
    </div>
  );
}
