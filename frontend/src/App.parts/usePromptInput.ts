import { useCallback, useState } from "react";

import type { PromptRequest } from "../components/PromptDialog";

export interface UsePromptInput {
  /** The active prompt request, or null when no dialog is open. */
  promptRequest: PromptRequest | null;
  /** Open a prompt and resolve with the entered string (or null on cancel). */
  promptInput: (opts: Omit<PromptRequest, "resolve">) => Promise<string | null>;
  /** Close the dialog (the PromptDialog calls this after resolving). */
  clearPrompt: () => void;
}

/**
 * Promise-based replacement for window.prompt (unsupported in Electron). Kept
 * out of App.tsx so the App component stays under the max-lines lint budget.
 */
export function usePromptInput(): UsePromptInput {
  const [promptRequest, setPromptRequest] = useState<PromptRequest | null>(null);
  const promptInput = useCallback(
    (opts: Omit<PromptRequest, "resolve">) =>
      new Promise<string | null>((resolve) => setPromptRequest({ ...opts, resolve })),
    [],
  );
  const clearPrompt = useCallback(() => setPromptRequest(null), []);
  return { promptRequest, promptInput, clearPrompt };
}
