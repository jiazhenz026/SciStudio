/**
 * ADR-053 spec 2 (#2001) — which agent runs the session, and how much it may do
 * without asking (FR-040 – FR-044).
 *
 * FR-042 — both controls are the EXISTING ones from
 * `AIChat/SetupScreen.parts/`, imported unchanged. Provider selection and
 * permission semantics belong to ADR-034; a second implementation here would
 * drift the moment a provider is added to the registry or a permission mode
 * changes, and the drift would be invisible until a user launched the wrong
 * thing. Nothing in this file forks either component — it supplies props.
 *
 * ONE DROPDOWN, NOT A DROPDOWN AND A PARAGRAPH (owner, 2026-08-08).
 *
 * This file used to render the usable providers in the picker and then a block
 * beneath it explaining every unusable one — its state, and the full remedy for
 * it. On a machine with two working agents and three that are not, that block
 * was four lines of install and login instructions for CLIs the user was not
 * going to use, sitting under a picker that already worked. The owner's verdict
 * was that it is filler, and that the AI chat already has the right shape: one
 * menu with every agent in it, the usable ones selectable, the rest greyed with
 * a short suffix saying why.
 *
 * So the list is gone and every provider is an option. The suffixes come from
 * `providerOptionOverrides`, which is also where the reasoning lives for why
 * `not_authenticated` is greyed HERE and selectable in the AI chat.
 *
 * WHAT DID NOT GO, AND MUST NOT. When NO provider is usable, the dialog renders
 * `AvailabilityGuidance` in place of this component entirely — full per-state
 * guidance naming a concrete next action. That is US3's dead end, it is what
 * FR-031 and SC-002 are written about, and both 2026-08-07 audits raised a P2
 * when it named no action. The two branches are not two styles of the same
 * message; they are answers to two different questions:
 *
 *   at least one usable  -> "which of these can I pick, and why not the rest?"
 *                           -> a menu annotation. THIS FILE.
 *   none usable          -> "I cannot proceed at all; what do I do?"
 *                           -> instructions. `AvailabilityGuidance`.
 *
 * A later reader tempted to unify them should note that the second branch is
 * the only one where the user has to act on the answer.
 */
import { PermissionModePicker } from "../AIChat/SetupScreen.parts/PermissionModePicker";
import { ProviderPicker } from "../AIChat/SetupScreen.parts/ProviderPicker";
import type { PermissionMode } from "../AIChat/SetupScreen.parts/types";

import { providerOptionOverrides, toProviderStatuses } from "./availability";
import type { AgentAvailabilityResponse } from "./useAgentAvailability";

/** The tab id the reused pickers namespace their element ids with. */
export const WORK_IMPORT_PICKER_ID = "work-import";

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
  const providers = availability?.providers ?? [];

  return (
    <div className="grid gap-4">
      {/*
       * FR-043 — with exactly one usable provider the parent has already
       * selected it, so this renders as a filled control rather than a
       * one-option menu. It stays visible either way: the user should be able
       * to see which agent is about to run, and which ones are not available.
       */}
      <ProviderPicker
        tabId={WORK_IMPORT_PICKER_ID}
        providers={toProviderStatuses(providers)}
        statusLoading={probing}
        provider={provider}
        onChange={onProviderChange}
        optionOverrides={providerOptionOverrides(availability)}
      />

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
