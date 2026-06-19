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
import type { TerminalTab as TerminalTabModel } from "../../store/types";
import { TerminalTab } from "./TerminalTab";
import { ConfirmDialog } from "./TerminalTabs.parts/ConfirmDialog";
import { TabStrip } from "./TerminalTabs.parts/TabStrip";

// Re-export so existing imports / tests continue to work; canonical home is
// blockPtyHandlers.ts (broken out to avoid the cycle with useWebSocket).
export { handleBlockPtyClosed, handleBlockPtyOpened } from "./blockPtyHandlers";

interface ShortcutHandlers {
  addTerminalTab: () => string;
  setActiveTerminalTab: (id: string) => void;
  requestCloseTab: (id: string) => void;
  activeTabId: string | null;
  tabs: TerminalTabModel[];
}

function useTabKeyboardShortcuts({
  addTerminalTab,
  setActiveTerminalTab,
  requestCloseTab,
  activeTabId,
  tabs,
}: ShortcutHandlers) {
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
}

interface CloseConfirmProps {
  pendingClose: string | null;
  tabs: TerminalTabModel[];
  onConfirm: (tabId: string, blockRunId: string | undefined, isAiBlock: boolean) => void;
  onCancel: () => void;
}

function PendingCloseDialog({ pendingClose, tabs, onConfirm, onCancel }: CloseConfirmProps) {
  if (!pendingClose) return null;
  const closingTab = tabs.find((t) => t.id === pendingClose);
  const isAiBlock = closingTab?.source === "ai-block";
  return (
    <ConfirmDialog
      message={
        isAiBlock
          ? "This AI Block is still running. Closing will cancel the block run."
          : "This terminal is still running. Closing will kill its subprocess."
      }
      onConfirm={() => onConfirm(pendingClose, closingTab?.blockRunId, isAiBlock)}
      onCancel={onCancel}
    />
  );
}

export function TerminalTabs() {
  const tabs = useAppStore((s) => s.terminalTabs);
  const activeTabId = useAppStore((s) => s.activeTerminalTabId);
  const addTerminalTab = useAppStore((s) => s.addTerminalTab);
  const addUserTerminalTab = useAppStore((s) => s.addUserTerminalTab);
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

  useTabKeyboardShortcuts({
    addTerminalTab,
    setActiveTerminalTab,
    requestCloseTab,
    activeTabId,
    tabs,
  });

  const commitRename = useCallback(() => {
    if (renamingId && renameDraft.trim().length > 0) {
      renameTerminalTab(renamingId, renameDraft.trim());
    }
    setRenamingId(null);
    setRenameDraft("");
  }, [renameDraft, renamingId, renameTerminalTab]);

  const cancelRename = useCallback(() => {
    setRenamingId(null);
    setRenameDraft("");
  }, []);

  const startRename = useCallback((id: string, title: string) => {
    setRenamingId(id);
    setRenameDraft(title);
  }, []);

  const handleConfirmClose = useCallback(
    (tabId: string, blockRunId: string | undefined, isAiBlock: boolean) => {
      // ADR-035 §3.9 — user-close-while-running emits cancel so the engine
      // can transition the block to CANCELLED and tear the PTY down cleanly.
      if (isAiBlock && blockRunId) {
        sendWebSocketMessage({
          type: "block_user_cancel",
          block_run_id: blockRunId,
          tab_id: tabId,
        });
      }
      closeTerminalTab(tabId);
      setPendingClose(null);
    },
    [closeTerminalTab],
  );

  return (
    <div className="flex h-full flex-col" data-testid="terminal-tabs">
      <TabStrip
        tabs={tabs}
        activeTabId={activeTabId}
        renamingId={renamingId}
        renameDraft={renameDraft}
        onSelect={setActiveTerminalTab}
        onStartRename={startRename}
        onRenameDraftChange={setRenameDraft}
        onRenameCommit={commitRename}
        onRenameCancel={cancelRename}
        onRequestClose={requestCloseTab}
        onAdd={() => {
          addTerminalTab();
        }}
        onAddUserTerminal={() => {
          addUserTerminalTab();
        }}
      />

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
            No active tab. Press <kbd className="mx-1 rounded bg-stone-200 px-1">Ctrl</kbd>+
            <kbd className="mx-1 rounded bg-stone-200 px-1">T</kbd> to open one.
          </div>
        ) : null}
      </div>

      <PendingCloseDialog
        pendingClose={pendingClose}
        tabs={tabs}
        onConfirm={handleConfirmClose}
        onCancel={() => setPendingClose(null)}
      />
    </div>
  );
}
