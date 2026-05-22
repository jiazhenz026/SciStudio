/**
 * ADR-034 Phase 1.3: TerminalTab — per-tab state-machine wrapper.
 *
 * Reads the tab's state from the Zustand `terminalTabsSlice` and renders
 * one of three sub-components:
 *   setup   -> <SetupScreen>
 *   running -> <TerminalView>
 *   closed  -> "Terminal exited (code N). [Reopen] [Close]"
 *
 * ADR-035 §3.9 skeleton extension:
 *   - Tabs spawned by an AI Block (tab.source === "ai-block") render a
 *     status badge (✓ DONE / ✗ ERROR / spinner PAUSED) inline with the
 *     title, and a "Mark done" button when the block is PAUSED.
 *   - Implementation phase (I35c) wires the badge + button to the
 *     tab.aiBlockStatus field on the tab state and the
 *     ``mark_done.json`` signal-write API.
 */
import { useCallback } from "react";

import { sendWebSocketMessage } from "../../hooks/useWebSocket";
import { useAppStore } from "../../store";
import { SetupScreen, type SetupLaunchConfig } from "./SetupScreen";
import { TerminalView } from "./TerminalView";

export interface TerminalTabProps {
  tabId: string;
}

/**
 * ADR-035 §3.9 — status badge for AI-Block-spawned tabs.
 *
 * Renders an inline glyph reflecting the block's current state:
 *   - "done"      → ✓  (emerald)
 *   - "error"     → ✗  (rose)
 *   - "cancelled" → ⊘  (stone, distinguishes from error)
 *   - "paused"    → spinner (amber, the dominant state during a run)
 *   - "running"   → green dot (transient state before PAUSED)
 *
 * Returns null when the tab is not AI-Block-sourced. The badge mirrors the
 * canvas BlockNode status pills (Tailwind palette) so the visual language
 * is consistent across the app.
 *
 * References: ADR-035 §3.9
 */
export function AiBlockStatusBadge({ tabId }: { tabId: string }): JSX.Element | null {
  const tab = useAppStore((s) => s.terminalTabs.find((t) => t.id === tabId));
  if (!tab || tab.source !== "ai-block") return null;
  const status = tab.blockStatus;
  const testid = `ai-block-status-badge-${tabId}`;
  if (status === "done") {
    return (
      <span
        className="ml-1 inline-block text-emerald-600"
        aria-label="AI Block done"
        data-testid={testid}
        data-status="done"
      >
        ✓
      </span>
    );
  }
  if (status === "error") {
    return (
      <span
        className="ml-1 inline-block text-rose-600"
        aria-label="AI Block error"
        data-testid={testid}
        data-status="error"
      >
        ✗
      </span>
    );
  }
  if (status === "cancelled") {
    return (
      <span
        className="ml-1 inline-block text-stone-500"
        aria-label="AI Block cancelled"
        data-testid={testid}
        data-status="cancelled"
      >
        ⊘
      </span>
    );
  }
  if (status === "paused") {
    return (
      <span
        className="ml-1 inline-block h-2 w-2 animate-spin rounded-full border border-amber-500 border-t-transparent align-middle"
        aria-label="AI Block paused — awaiting completion"
        data-testid={testid}
        data-status="paused"
      />
    );
  }
  // status === "running" or undefined — show a small live dot
  return (
    <span
      className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 align-middle"
      aria-label="AI Block running"
      data-testid={testid}
      data-status={status ?? "unknown"}
    />
  );
}

/**
 * ADR-035 §3.5 path (c) — "Mark done" escape-hatch button.
 *
 * Visible only when the tab was spawned by an AI Block AND the block is
 * currently in PAUSED state. On click sends a `block_user_marked_done` WS
 * message addressed to the originating block run; the engine (I35b) writes
 * a `mark_done.json` signal file the worker's CompletionWatcher polls.
 *
 * The button is rendered ONLY in the running TerminalView tab content
 * (not in the tab strip) so it sits next to the agent's PTY where the user
 * is actively reading the agent's output.
 *
 * References: ADR-035 §3.5 path (c), §3.9
 */
export function MarkDoneButton({ tabId }: { tabId: string }): JSX.Element | null {
  const tab = useAppStore((s) => s.terminalTabs.find((t) => t.id === tabId));
  if (!tab) return null;
  if (tab.source !== "ai-block") return null;
  if (tab.blockStatus !== "paused") return null;
  const handleClick = () => {
    if (!tab.blockRunId) return;
    sendWebSocketMessage({
      type: "block_user_marked_done",
      block_run_id: tab.blockRunId,
      tab_id: tab.id,
    });
  };
  return (
    <button
      type="button"
      className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-medium text-white shadow-sm hover:bg-emerald-700"
      onClick={handleClick}
      data-testid={`mark-done-btn-${tabId}`}
    >
      Mark done
    </button>
  );
}

export function TerminalTab({ tabId }: TerminalTabProps) {
  const tab = useAppStore((s) => s.terminalTabs.find((t) => t.id === tabId));
  const projectPath = useAppStore((s) => s.currentProject?.path ?? null);
  const launchTerminalTab = useAppStore((s) => s.launchTerminalTab);
  const markTerminalTabExited = useAppStore((s) => s.markTerminalTabExited);
  const closeTerminalTab = useAppStore((s) => s.closeTerminalTab);
  const reopenTerminalTab = useAppStore((s) => s.reopenTerminalTab);

  const handleLaunch = useCallback(
    (config: SetupLaunchConfig) => {
      launchTerminalTab(tabId, config.provider, config.dangerous ? "dangerous" : "safe");
    },
    [launchTerminalTab, tabId],
  );

  const handleCancel = useCallback(() => {
    closeTerminalTab(tabId);
  }, [closeTerminalTab, tabId]);

  const handleExit = useCallback(
    (code: number) => {
      markTerminalTabExited(tabId, code);
    },
    [markTerminalTabExited, tabId],
  );

  const handleError = useCallback(
    (message: string) => {
      // Map errors to an immediate close with synthetic code -1 and store
      // the message so the closed-screen can show it. We piggy-back on
      // exitCode -1 == reload / error; a richer model can ship later.
      // Surfaced via the console for now so smoke testers can see it.
      // TODO: build a structured error model (separate exit-vs-error states, surface in tab UI instead of console).
      // eslint-disable-next-line no-console
      console.error(`[TerminalTab ${tabId}] WS error:`, message);
      markTerminalTabExited(tabId, -1);
    },
    [markTerminalTabExited, tabId],
  );

  if (!tab) {
    return (
      <div
        className="flex h-full items-center justify-center text-sm text-stone-400"
        data-testid={`terminal-tab-missing-${tabId}`}
      >
        Tab not found.
      </div>
    );
  }

  if (tab.state === "setup") {
    return <SetupScreen tabId={tabId} onLaunch={handleLaunch} onCancel={handleCancel} />;
  }

  if (tab.state === "running") {
    if (!projectPath || !tab.provider) {
      // Belt-and-braces guard: we should never end up "running" without
      // these, but if rehydration leaves the state inconsistent, show a
      // friendly fallback instead of crashing the xterm mount.
      return (
        <div className="flex h-full items-center justify-center text-sm text-stone-500">
          Missing working directory or provider. Reopen the tab to retry.
        </div>
      );
    }
    // ADR-035 §3.5 (c) / §3.9 — for AI-Block tabs, overlay a floating
    // "Mark done" pill in the upper-right corner when the block is paused.
    // Keeps TerminalView (xterm) logic untouched per dispatch scope.
    return (
      <div className="relative h-full" data-testid={`terminal-tab-running-${tabId}`}>
        <TerminalView
          tabId={tabId}
          projectDir={projectPath}
          provider={tab.provider}
          dangerous={tab.permissionMode === "dangerous"}
          onExit={handleExit}
          onError={handleError}
        />
        {tab.source === "ai-block" ? (
          <div className="pointer-events-none absolute right-3 top-2 z-10">
            <div className="pointer-events-auto">
              <MarkDoneButton tabId={tabId} />
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  // closed
  const code = tab.exitCode ?? 0;
  const reloadSynthetic = code === -1;
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-3 px-6 text-sm"
      data-testid={`terminal-tab-closed-${tabId}`}
    >
      <p className="text-stone-600">
        {reloadSynthetic
          ? "Terminal exited (page reload — subprocess did not survive)."
          : `Terminal exited (code ${code}).`}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded-full bg-ink px-4 py-2 text-white hover:bg-stone-800"
          onClick={() => reopenTerminalTab(tabId)}
          data-testid={`terminal-tab-reopen-${tabId}`}
        >
          Reopen
        </button>
        <button
          type="button"
          className="rounded-full border border-stone-300 px-4 py-2 text-stone-600 hover:bg-stone-50"
          onClick={() => closeTerminalTab(tabId)}
          data-testid={`terminal-tab-close-${tabId}`}
        >
          Close
        </button>
      </div>
    </div>
  );
}
