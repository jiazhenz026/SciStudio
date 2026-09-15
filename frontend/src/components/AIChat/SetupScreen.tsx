/**
 * ADR-034 Phase 1.3: SetupScreen — provider + permission-mode picker.
 *
 * Renders before a terminal tab is launched. Fetches `/api/ai/status` on
 * mount to disable providers that aren't installed and surface a
 * "(not logged in)" hint for providers that are installed but unauthenticated.
 */
import { useState } from "react";

import { useAppStore } from "../../store";
import { AgentLaunchSetup } from "./SetupScreen.parts/AgentLaunchSetup";
import {
  _resetAgentStatusCache,
  agentLaunchProblem,
  useAgentStatus,
} from "./SetupScreen.parts/agentStatus";
import type { PermissionMode, TerminalProvider } from "./SetupScreen.parts/types";

export interface SetupLaunchConfig {
  provider: TerminalProvider;
  /** #2379 — Manual (`safe`), Auto (`auto`) or Yolo/Bypass (`dangerous`). */
  permissionMode: PermissionMode;
}

export interface SetupScreenProps {
  /** ID of the parent terminal tab. Used only for accessibility / labelling. */
  tabId: string;
  onLaunch: (config: SetupLaunchConfig) => void;
  onCancel: () => void;
}

/** Test-only: reset the shared status cache. Not exported via index. */
export function _resetSetupStatusCache(): void {
  _resetAgentStatusCache();
}

export function SetupScreen({ tabId, onLaunch, onCancel }: SetupScreenProps) {
  const currentProject = useAppStore((s) => s.currentProject);
  const projectPath = currentProject?.path ?? null;

  const agentStatus = useAgentStatus();
  const [provider, setProvider] = useState<TerminalProvider | null>(null);
  const [permissionMode, setPermissionMode] = useState<PermissionMode | null>(null);

  const launchDisabled =
    !projectPath || agentLaunchProblem(agentStatus.providers, provider, permissionMode) !== null;

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden px-4 py-3"
      data-testid={`setup-screen-${tabId}`}
    >
      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1"
        data-testid="setup-scroll-body"
      >
        <AgentLaunchSetup
          tabId={tabId}
          agentStatus={agentStatus}
          provider={provider}
          permissionMode={permissionMode}
          onProviderChange={setProvider}
          onPermissionModeChange={setPermissionMode}
        />

        <div
          className="rounded-2xl border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-600"
          data-testid="setup-working-dir"
        >
          Working dir:{" "}
          <span className="font-mono">
            {projectPath ?? <em className="text-stone-400">(no project open)</em>}
          </span>
        </div>
      </div>

      <div
        className="flex shrink-0 items-center justify-end gap-2 border-t border-stone-200 pt-3"
        data-testid="setup-actions"
      >
        <button
          type="button"
          className="rounded-full border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
          onClick={onCancel}
          data-testid="setup-cancel"
        >
          Cancel
        </button>
        <button
          type="button"
          className={`rounded-full px-4 py-2 text-sm text-white ${
            launchDisabled ? "bg-stone-300" : "bg-ink hover:bg-stone-800"
          }`}
          disabled={launchDisabled}
          data-testid="setup-launch"
          onClick={() => {
            if (provider && permissionMode) {
              onLaunch({ provider, permissionMode });
            }
          }}
        >
          Launch ▸
        </button>
      </div>
    </div>
  );
}
