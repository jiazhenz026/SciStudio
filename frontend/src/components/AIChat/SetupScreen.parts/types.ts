/**
 * Shared types for SetupScreen and its parts.
 *
 * Extracted in #1413 to allow ProviderPicker / PermissionModePicker to live in
 * their own files without forcing a circular import.
 */
export type ProviderName = "claude-code" | "codex";

export interface ProviderStatus {
  name: ProviderName;
  available: boolean;
  version: string | null;
  logged_in: boolean;
}

export interface AiStatusResponse {
  providers: ProviderStatus[];
}

export type PermissionMode = "safe" | "dangerous";
