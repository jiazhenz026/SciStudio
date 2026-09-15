/**
 * Shared types for SetupScreen and its parts.
 *
 * Extracted in #1413 to allow ProviderPicker / PermissionModePicker to live in
 * their own files without forcing a circular import.
 *
 * ADR-034 FR-020: this module no longer declares a provider union or a status
 * shape of its own. `store/types.ts` is the single source; everything provider-
 * related is re-exported from there so Setup-screen consumers keep a local
 * import path without a second declaration drifting out of sync.
 */
export type {
  AgentProviderKey,
  AiStatusResponse,
  ProviderStatus,
  TerminalProvider,
  UserTerminalProvider,
} from "../../../store/types";

export {
  isKnownAgentProvider,
  isTerminalProviderKey,
  isUserTerminalProvider,
  USER_TERMINAL_PROVIDER,
} from "../../../store/types";

/**
 * How a launched session starts: `safe` is Manual, `auto` is Auto, and
 * `dangerous` is Yolo/Bypass (ADR-034 Addendum 1, #2379). The backend spells
 * `dangerous` as `bypass`; the mapping happens at each request boundary.
 */
export type PermissionMode = "safe" | "auto" | "dangerous";
