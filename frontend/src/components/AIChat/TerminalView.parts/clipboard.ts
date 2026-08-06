/**
 * ADR-034 — clipboard plumbing for the embedded PTY terminal (#1994).
 *
 * SciStudio's terminal users are scientists, not CLI users. They press Ctrl+C
 * expecting "copy"; the terminal's historical meaning (send SIGINT) killed
 * their agent session with no explanation. Per the owner decision on #1994 the
 * PTY now treats Ctrl+C / Ctrl+V as copy / paste, and closing a session is done
 * with the tab's X button instead.
 *
 * This module holds only the browser-clipboard side of that: the async
 * `navigator.clipboard` calls plus the classification of their failure modes
 * into short user-facing hints. Keeping it free of React and of xterm makes
 * both the key handler and the context menu in TerminalView.tsx reuse the exact
 * same semantics, and makes the denial paths directly unit-testable.
 *
 * The Clipboard API is async and refusable: it rejects on a denied permission,
 * and it is entirely absent outside a secure context (plain http:// on a
 * non-localhost origin). Neither case may throw into the console or silently
 * do nothing, so every call site gets a status back and shows a hint.
 */

/**
 * Outcome of a clipboard interaction.
 *
 *   ok          — the text was copied / read.
 *   empty       — nothing to act on (no selection, or an empty clipboard).
 *   denied      — the API exists but rejected (permission denied, or the
 *                 document was not focused when the call was made).
 *   unavailable — `navigator.clipboard` (or the needed method) does not exist,
 *                 i.e. an insecure origin or an old browser.
 */
export type ClipboardStatus = "ok" | "empty" | "denied" | "unavailable";

export interface ClipboardReadResult {
  status: ClipboardStatus;
  text: string;
}

function clipboardApi(): Clipboard | null {
  if (typeof navigator === "undefined") return null;
  return (navigator as Navigator & { clipboard?: Clipboard }).clipboard ?? null;
}

/**
 * Write `text` to the system clipboard.
 *
 * An empty `text` is reported as "empty" rather than written: clearing the
 * user's clipboard because their selection happened to be empty would be a
 * destructive surprise.
 */
export async function copyTextToClipboard(text: string): Promise<ClipboardStatus> {
  if (!text) return "empty";
  const clipboard = clipboardApi();
  if (typeof clipboard?.writeText !== "function") return "unavailable";
  try {
    await clipboard.writeText(text);
    return "ok";
  } catch {
    return "denied";
  }
}

/**
 * True when the browser lets page script READ the clipboard.
 *
 * Firefox deliberately exposes `readText()` to extensions only, and any
 * insecure origin has no Clipboard API at all. Where we cannot read, we must
 * NOT claim the Ctrl+V keystroke: the browser's own paste (which xterm turns
 * into stdin through its paste event) is the only path that still works, and
 * calling preventDefault would remove it and leave the user unable to paste.
 */
export function canReadClipboard(): boolean {
  return typeof clipboardApi()?.readText === "function";
}

/** Read the system clipboard, classifying denial / absence instead of throwing. */
export async function readTextFromClipboard(): Promise<ClipboardReadResult> {
  const clipboard = clipboardApi();
  if (typeof clipboard?.readText !== "function") return { status: "unavailable", text: "" };
  try {
    const text = await clipboard.readText();
    if (!text) return { status: "empty", text: "" };
    return { status: "ok", text };
  } catch {
    return { status: "denied", text: "" };
  }
}

/**
 * Hint shown after a copy attempt, or null when the outcome needs no words.
 *
 * "empty" is deliberately NOT silent. Ctrl+C no longer interrupts the process,
 * so with no selection the key would otherwise appear to do nothing at all —
 * exactly the confusion #1994 is fixing. The hint tells the user why.
 */
export function copyHint(status: ClipboardStatus): string | null {
  switch (status) {
    case "ok":
      return "Copied to clipboard";
    case "empty":
      return "Nothing selected — select text first, then press Ctrl+C to copy.";
    case "denied":
      return "Clipboard permission denied — could not copy.";
    case "unavailable":
      return "Clipboard is unavailable here (needs a secure page).";
  }
}

/**
 * Hint shown after a paste attempt.
 *
 * A successful paste needs no hint: the pasted characters are their own
 * feedback, and a toast on every paste would be noise.
 */
export function pasteHint(status: ClipboardStatus): string | null {
  switch (status) {
    case "ok":
      return null;
    case "empty":
      return "Clipboard is empty — nothing to paste.";
    case "denied":
      return "Clipboard permission denied — could not paste.";
    case "unavailable":
      return "Clipboard is unavailable here (needs a secure page).";
  }
}
