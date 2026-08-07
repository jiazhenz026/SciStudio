/**
 * ADR-053 spec 2 (#2001) — which agent runs the session, and how much it may do
 * without asking (FR-040 – FR-044).
 *
 * FR-042 — both controls are the EXISTING ones from
 * `AIChat/SetupScreen.parts/`, imported unchanged. Provider selection and
 * permission semantics belong to ADR-034; a second implementation here would
 * drift the moment a provider is added to the registry or a permission mode
 * changes, and the drift would be invisible until a user launched the wrong
 * thing. Nothing in this file forks either component — it only supplies props.
 */
import { PermissionModePicker } from "../AIChat/SetupScreen.parts/PermissionModePicker";
import { ProviderPicker } from "../AIChat/SetupScreen.parts/ProviderPicker";
import type { PermissionMode } from "../AIChat/SetupScreen.parts/types";

import { PARTIAL_AVAILABILITY_NOTE } from "./copy";
import { toProviderStatuses, unusableProviders, usableProviders } from "./availability";
import type { AgentAvailabilityResponse, ProviderAvailability } from "./useAgentAvailability";

/** The tab id the reused pickers namespace their element ids with. */
export const WORK_IMPORT_PICKER_ID = "work-import";

const STATE_SUMMARY: Record<string, string> = {
  not_installed: "not found on this computer",
  not_authenticated: "not signed in",
  call_failed: "a test call failed",
};

/** Summary for a provider that works but cannot be handed a task to start with. */
const SESSION_UNSUPPORTED_SUMMARY = "cannot be started with a task";

function unusableLine(provider: ProviderAvailability): string {
  // A provider that cannot run a session is reported as that rather than by its
  // availability state: it may well be `ready`, and "Kimi Code — ready" in a
  // list headed "not usable right now" reads as a bug rather than as a fact.
  if (provider.session_unsupported_reason) {
    return `${provider.label} — ${SESSION_UNSUPPORTED_SUMMARY}: ${provider.session_unsupported_reason}`;
  }
  const summary = STATE_SUMMARY[provider.state] ?? provider.state;
  const detail = provider.state === "call_failed" ? provider.cause : provider.next_step;
  return detail ? `${provider.label} — ${summary}: ${detail}` : `${provider.label} — ${summary}`;
}

export interface AgentSetupProps {
  availability: AgentAvailabilityResponse | null;
  probing: boolean;
  provider: string | null;
  permissionMode: PermissionMode;
  onProviderChange: (provider: string) => void;
  onPermissionModeChange: (mode: PermissionMode) => void;
}

export function AgentSetup({
  availability,
  probing,
  provider,
  permissionMode,
  onProviderChange,
  onPermissionModeChange,
}: AgentSetupProps) {
  const usable = usableProviders(availability);
  const unusable = unusableProviders(availability);

  return (
    <div className="grid gap-4">
      {/*
       * FR-043 — with exactly one usable provider the parent has already
       * selected it, so this renders as a filled control rather than a
       * one-option menu. It stays visible either way: the user should be able
       * to see which agent is about to run.
       */}
      <ProviderPicker
        tabId={WORK_IMPORT_PICKER_ID}
        providers={toProviderStatuses(usable)}
        statusLoading={probing}
        provider={provider}
        onChange={onProviderChange}
      />

      {/*
       * FR-005 — a mixed result must not block. The usable agents stay
       * selectable above and the rest are reported here, with their real state
       * and their real cause, as information rather than as an obstacle.
       */}
      {usable.length > 0 && unusable.length > 0 ? (
        <div className="text-xs text-stone-500" data-testid="work-import-unusable-providers">
          <p>{PARTIAL_AVAILABILITY_NOTE}</p>
          <ul className="mt-1 list-disc pl-5">
            {unusable.map((p) => (
              <li key={p.key || p.label}>{unusableLine(p)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/*
       * FR-041 — a session that writes many files and runs the user's code hits
       * permission prompts constantly. A user who wants to grant that up front
       * must be able to; a user who does not keeps the safe default.
       */}
      <PermissionModePicker
        tabId={WORK_IMPORT_PICKER_ID}
        permissionMode={permissionMode}
        onChange={onPermissionModeChange}
      />
    </div>
  );
}
