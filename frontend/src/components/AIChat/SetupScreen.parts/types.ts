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
import type { TerminalProvider } from "../../../store/types";

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
 * @deprecated ADR-034 FR-020 — transitional alias for `TerminalProvider`.
 *
 * Kept only so the Setup-screen components keep compiling while they are
 * migrated to `TerminalProvider` in the same change set. It is an alias, not a
 * second declaration; delete it once no consumer references it.
 */
export type ProviderName = TerminalProvider;

export type PermissionMode = "safe" | "dangerous";
