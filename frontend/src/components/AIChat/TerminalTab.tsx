/**
 * ADR-034 Phase 1.3: TerminalTab — per-tab state-machine wrapper.
 *
 * Reads the tab's state from the Zustand `terminalTabsSlice` and renders
 * one of three sub-components:
 *   setup   -> <SetupScreen>
 *   running -> <TerminalView>
 *   closed  -> "Terminal exited (code N). [Reopen] [Close]"
 */
import { useCallback } from "react";

import { useAppStore } from "../../store";
import { SetupScreen, type SetupLaunchConfig } from "./SetupScreen";
import { TerminalView } from "./TerminalView";

export interface TerminalTabProps {
  tabId: string;
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
