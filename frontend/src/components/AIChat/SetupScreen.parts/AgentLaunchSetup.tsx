/**
 * The agent half of every session-starting surface: provider and permission mode.
 *
 * #2454 (owner directive): AI Chat and the dialogs that start a session must be
 * exactly the same, with no second implementation. This is AI Chat's setup body
 * — status error, the zero-install notice or the provider picker, the per-CLI
 * notes, and the permission-mode picker — lifted out of `SetupScreen` so the New
 * MiniApp, Convert to interactive block and Bring in my work dialogs render it
 * unchanged. The surface owns the chosen values and its own action button; the
 * status comes from `useAgentStatus`.
 */
import { NoProvidersNotice } from "./NoProvidersNotice";
import { PermissionModePicker } from "./PermissionModePicker";
import { ProviderPicker } from "./ProviderPicker";
import type { AgentStatus } from "./agentStatus";
import type { PermissionMode, TerminalProvider } from "./types";

export interface AgentLaunchSetupProps {
  /** Namespaces the pickers' element ids. */
  tabId: string;
  agentStatus: AgentStatus;
  provider: TerminalProvider | null;
  permissionMode: PermissionMode | null;
  onProviderChange: (provider: TerminalProvider) => void;
  onPermissionModeChange: (mode: PermissionMode) => void;
}

export function AgentLaunchSetup({
  tabId,
  agentStatus,
  provider,
  permissionMode,
  onProviderChange,
  onPermissionModeChange,
}: AgentLaunchSetupProps) {
  const { status, statusError, statusLoading, providers } = agentStatus;

  /**
   * ADR-034 FR-021d — `statusLoaded` is true only once the payload actually
   * arrived, so "unknown availability" (in flight or failed) can never be
   * mistaken for "confirmed absence".
   */
  const statusLoaded = !statusLoading && statusError === null && status !== null;
  /** FR-021c — the loaded-and-all-unavailable branch, and only that branch. */
  const noProvidersAvailable = statusLoaded && providers.every((p) => !p.available);
  const selectedProviderStatus = providers.find((p) => p.name === provider);

  return (
    <div className="grid gap-4" data-testid="agent-launch-setup">
      {statusError ? (
        <div
          className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          data-testid="setup-status-error"
        >
          Could not check provider status ({statusError}). Launch will be disabled until
          /api/ai/status is reachable.
        </div>
      ) : null}

      {noProvidersAvailable ? (
        <NoProvidersNotice providers={providers} />
      ) : (
        <ProviderPicker
          tabId={tabId}
          providers={providers}
          statusLoading={statusLoading}
          provider={provider}
          onChange={onProviderChange}
        />
      )}

      {/* #1859: Codex asks the user to trust this project's hooks on first
          launch. Non-technical users may not know what hooks are; if they
          decline, SciStudio's safety hooks (e.g. the data/ guard) never run.
          We surface a short note rather than silently editing global config. */}
      {provider === "codex" ? (
        <div
          className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          data-testid="setup-codex-trust-note"
        >
          <strong className="font-medium">Heads up:</strong> the first time Codex launches in this
          project it will ask whether to trust its hooks. Please choose{" "}
          <strong className="font-medium">trust / yes</strong> — SciStudio installs safety hooks
          (such as protecting your <span className="font-mono">data/</span> folder from accidental
          edits) that only take effect if you accept.
        </div>
      ) : null}

      {/* #2045: Kimi Code reads hooks only from its user-level config, so there
          is no project-scope file SciStudio can drop hooks into and this session
          runs unguarded. Writing the user's global config on their behalf was
          rejected, which leaves saying so plainly. */}
      {provider === "kimi-code" ? (
        <div
          className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          data-testid="setup-kimi-hooks-note"
        >
          <strong className="font-medium">Heads up:</strong> Kimi Code reads hooks only from its own
          user-level <span className="font-mono">config.toml</span>, so SciStudio&rsquo;s safety
          hooks — the ones that keep your <span className="font-mono">data/</span> folder and
          workflow files from being edited by accident — do not apply to this tab. You can add them
          by hand, or simply ask Kimi in this tab to set them up for you. They would then apply to{" "}
          <strong className="font-medium">every</strong> Kimi Code session on this machine, not just
          this project.
        </div>
      ) : null}

      <PermissionModePicker
        tabId={tabId}
        permissionMode={permissionMode}
        onChange={onPermissionModeChange}
        autoSupported={selectedProviderStatus?.supports_auto_mode === true}
      />
    </div>
  );
}
