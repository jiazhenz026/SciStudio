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

/**
 * What the terminal should do with a key event, decided without touching React
 * or xterm so the same predicate can be exercised in a real browser.
 *
 *   "copy"   — Ctrl/Cmd+C: claim it, cancel the default, copy the selection.
 *   "paste"  — Ctrl/Cmd+V: claim it so xterm does not encode \x16, but leave
 *              the default alone so the browser's own (permission-free) paste
 *              runs and xterm's paste listener forwards it to the PTY.
 *   "ignore" — everything else, including Ctrl+Shift+C/V and the tab shortcuts.
 */
export type ClipboardKeyAction = "copy" | "paste" | "ignore";

export function classifyClipboardKey(ev: {
  type: string;
  key?: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
}): ClipboardKeyAction {
  // xterm calls the custom handler for keydown/keypress/keyup; act once.
  if (ev.type !== "keydown") return "ignore";
  if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return "ignore";
  const key = ev.key?.toLowerCase();
  if (key === "c") return "copy";
  if (key === "v") return "paste";
  return "ignore";
}

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
 * Read the system clipboard, classifying denial / absence instead of throwing.
 *
 * Only the right-click Paste item uses this. Ctrl+V does NOT: a menu click is
 * not a paste gesture, so the menu has no alternative, whereas Ctrl+V can ride
 * the browser's own permission-free paste event. See useTerminalClipboard.
 *
 * `readText()` is far more restricted than `writeText()`: writing is allowed on
 * transient user activation, but reading needs the `clipboard-read` permission,
 * which is "prompt" by default and simply rejects until granted. That asymmetry
 * is why copy worked while paste did not (#1994 follow-up).
 */
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
 * Hint shown after a right-click Paste attempt.
 *
 * A successful paste needs no hint: the pasted characters are their own
 * feedback, and a toast on every paste would be noise.
 *
 * The failure hints point at Ctrl+V rather than just apologising. Ctrl+V does
 * not go through the Clipboard API at all, so it still works when reading is
 * denied — that makes it a real instruction, not a consolation.
 */
export function pasteHint(status: ClipboardStatus): string | null {
  switch (status) {
    case "ok":
      return null;
    case "empty":
      return "Clipboard is empty — nothing to paste.";
    case "denied":
      return "Clipboard read not permitted here — press Ctrl+V to paste instead.";
    case "unavailable":
      return "Clipboard read is unavailable here — press Ctrl+V to paste instead.";
  }
}
