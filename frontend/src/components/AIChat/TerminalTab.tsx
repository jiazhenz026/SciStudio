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

import { useAppStore } from "../../store";
import { SetupScreen, type SetupLaunchConfig } from "./SetupScreen";
import { TerminalView } from "./TerminalView";

export interface TerminalTabProps {
  tabId: string;
}

/**
 * ADR-035 §3.9 skeleton: status badge for AI-Block-spawned tabs.
 *
 * Implementation plan (I35c):
 *   - Read `tab.source` and `tab.aiBlockStatus` from the store.
 *   - Render one of: ✓ (DONE), ✗ (ERROR), ⏳ (PAUSED), nothing (RUNNING).
 *   - Tailwind classes mirror the canvas BlockNode status pills so the
 *     visual language is consistent.
 *
 * Test plan (vitest):
 *   - test_renders_done_badge_when_status_done
 *   - test_renders_error_badge_when_status_error
 *   - test_renders_spinner_when_status_paused
 *   - test_renders_nothing_when_source_not_ai_block
 *
 * References: ADR-035 §3.9
 */
export function AiBlockStatusBadge(_props: { tabId: string }): JSX.Element | null {
  // SKELETON: returns null until I35c wires real status from the store.
  // See comment block above.
  return null;
}

/**
 * ADR-035 §3.5 path (c) skeleton: "Mark done" escape-hatch button.
 *
 * Implementation plan (I35c):
 *   - Visible when `tab.source === "ai-block"` && `tab.aiBlockStatus === "paused"`.
 *   - On click, POST to `/api/blocks/ai/{block_run_id}/mark_done` (engine
 *     route added in I35b) — engine writes the `mark_done.json` signal
 *     file under the run_dir, the worker's CompletionWatcher picks it up.
 *   - Button is disabled (with tooltip) outside paused state.
 *
 * Test plan (vitest):
 *   - test_button_visible_when_ai_block_paused
 *   - test_button_hidden_when_not_ai_block_tab
 *   - test_button_click_calls_mark_done_api
 *
 * References: ADR-035 §3.5 path (c), §3.9
 */
export function MarkDoneButton(_props: { tabId: string }): JSX.Element | null {
  // SKELETON: returns null until I35c wires the API call.
  // See comment block above.
  return null;
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
    return (
      <SetupScreen tabId={tabId} onLaunch={handleLaunch} onCancel={handleCancel} />
    );
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
    return (
      <TerminalView
        tabId={tabId}
        projectDir={projectPath}
        provider={tab.provider}
        dangerous={tab.permissionMode === "dangerous"}
        onExit={handleExit}
        onError={handleError}
      />
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
