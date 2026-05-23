/**
 * ADR-034 Phase 1.3: SetupScreen — provider + permission-mode picker.
 *
 * Renders before a terminal tab is launched. Fetches `/api/ai/status` on
 * mount to disable providers that aren't installed and surface a
 * "(not logged in)" hint for providers that are installed but unauthenticated.
 */
import { useEffect, useMemo, useState } from "react";

import { useAppStore } from "../../store";
import { PermissionModePicker } from "./SetupScreen.parts/PermissionModePicker";
import { ProviderPicker } from "./SetupScreen.parts/ProviderPicker";
import type {
  AiStatusResponse,
  PermissionMode,
  ProviderName,
  ProviderStatus,
} from "./SetupScreen.parts/types";

export interface SetupLaunchConfig {
  provider: ProviderName;
  dangerous: boolean;
}

export interface SetupScreenProps {
  /** ID of the parent terminal tab. Used only for accessibility / labelling. */
  tabId: string;
  onLaunch: (config: SetupLaunchConfig) => void;
  onCancel: () => void;
}

// Module-level cache (30s TTL). Multiple SetupScreens mounted within 30s share
// the same in-flight / cached payload.
let _statusCache: { at: number; data: AiStatusResponse } | null = null;
let _statusInflight: Promise<AiStatusResponse> | null = null;

async function fetchStatus(force = false): Promise<AiStatusResponse> {
  const now = Date.now();
  if (!force && _statusCache && now - _statusCache.at < 30_000) {
    return _statusCache.data;
  }
  if (_statusInflight) return _statusInflight;
  _statusInflight = (async () => {
    try {
      const r = await fetch("/api/ai/status");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as AiStatusResponse;
      _statusCache = { at: Date.now(), data };
      return data;
    } finally {
      _statusInflight = null;
    }
  })();
  return _statusInflight;
}

/** Test-only: reset module cache. Not exported via index. */
export function _resetSetupStatusCache(): void {
  _statusCache = null;
  _statusInflight = null;
}

interface UseSetupStatusResult {
  status: AiStatusResponse | null;
  statusError: string | null;
  statusLoading: boolean;
}

function useSetupStatus(): UseSetupStatusResult {
  const [status, setStatus] = useState<AiStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchStatus();
        if (!cancelled) {
          setStatus(data);
          setStatusError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setStatusError(err instanceof Error ? err.message : "status unavailable");
        }
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, statusError, statusLoading };
}

export function SetupScreen({ tabId, onLaunch, onCancel }: SetupScreenProps) {
  const currentProject = useAppStore((s) => s.currentProject);
  const projectPath = currentProject?.path ?? null;

  const { status, statusError, statusLoading } = useSetupStatus();
  const [provider, setProvider] = useState<ProviderName | null>(null);
  const [permissionMode, setPermissionMode] = useState<PermissionMode | null>(null);

  const providersByName = useMemo(() => {
    const map: Partial<Record<ProviderName, ProviderStatus>> = {};
    for (const p of status?.providers ?? []) map[p.name] = p;
    return map;
  }, [status]);

  const selectedProviderStatus = provider ? providersByName[provider] : undefined;
  const launchDisabled =
    !provider ||
    !permissionMode ||
    !projectPath ||
    (selectedProviderStatus !== undefined && !selectedProviderStatus.available);

  return (
    <div
      className="flex h-full flex-col gap-4 overflow-y-auto px-4 py-3"
      data-testid={`setup-screen-${tabId}`}
    >
      <h3 className="text-base font-semibold text-ink">New chat — Setup</h3>

      {statusError ? (
        <div
          className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          data-testid="setup-status-error"
        >
          Could not check provider status ({statusError}). Launch will be disabled until
          /api/ai/status is reachable.
        </div>
      ) : null}

      <ProviderPicker
        tabId={tabId}
        claudeStatus={providersByName["claude-code"]}
        codexStatus={providersByName["codex"]}
        statusLoading={statusLoading}
        provider={provider}
        onChange={setProvider}
      />

      <PermissionModePicker
        tabId={tabId}
        permissionMode={permissionMode}
        onChange={setPermissionMode}
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

      <div className="mt-auto flex items-center justify-end gap-2 pt-2">
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
              onLaunch({ provider, dangerous: permissionMode === "dangerous" });
            }
          }}
        >
          Launch ▸
        </button>
      </div>
    </div>
  );
}
