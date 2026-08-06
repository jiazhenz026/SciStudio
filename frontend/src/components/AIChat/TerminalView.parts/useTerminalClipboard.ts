/**
 * ADR-034 — clipboard behaviour for the embedded PTY terminal (#1994).
 *
 * Owner decision: SciStudio's terminal users are scientists, not CLI users.
 * Ctrl+C used to reach the PTY as SIGINT and kill their agent mid-conversation
 * while they believed they were copying. Ctrl+C now means COPY and Ctrl+V means
 * PASTE; the terminal loses its interrupt gesture on purpose, and a session is
 * ended with the tab's X button. Right-click offers the same two actions.
 *
 * This hook owns all of that state so TerminalView keeps its xterm lifecycle
 * effect readable. It returns a STABLE `handleTerminalKeyEvent`, because
 * TerminalView installs it exactly once via xterm's
 * `attachCustomKeyEventHandler` from the mount effect.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { PtyClientFrame } from "../hooks/usePtyWebSocket";
import {
  canReadClipboard,
  copyHint,
  copyTextToClipboard,
  pasteHint,
  readTextFromClipboard,
} from "./clipboard";

// How long a clipboard hint ("Copied", "Nothing selected", a denial) stays up.
const CLIPBOARD_HINT_MS = 2200;

/** The slice of the xterm API this hook drives. */
interface ClipboardCapableTerm {
  getSelection?: () => string;
  hasSelection?: () => boolean;
  paste?: (data: string) => void;
}

export interface TerminalContextMenuState {
  /** Position within the terminal frame, in px. */
  x: number;
  y: number;
  /** False when the terminal has no selection — Copy is then disabled. */
  canCopy: boolean;
}

export interface UseTerminalClipboardParams {
  /** Mutable ref holding the live xterm Terminal (null before it mounts). */
  termRef: React.MutableRefObject<unknown>;
  /** The `relative` frame the context menu is positioned inside. */
  frameRef: React.MutableRefObject<HTMLDivElement | null>;
  /** PTY stdin sender; the fallback path when xterm exposes no paste(). */
  send: (frame: PtyClientFrame) => void;
}

export interface UseTerminalClipboardResult {
  clipboardHint: string | null;
  contextMenu: TerminalContextMenuState | null;
  handleContextMenu: (ev: React.MouseEvent<HTMLDivElement>) => void;
  closeContextMenu: () => void;
  handleMenuCopy: () => void;
  handleMenuPaste: () => void;
  /**
   * xterm custom key-event handler. Returns false for the keys we claim, which
   * is what stops xterm translating them into PTY bytes.
   */
  handleTerminalKeyEvent: (ev: KeyboardEvent) => boolean;
}

export function useTerminalClipboard({
  termRef,
  frameRef,
  send,
}: UseTerminalClipboardParams): UseTerminalClipboardResult {
  // Transient one-line hint over the terminal. Every clipboard path reports
  // through here, including the ones that "succeed at doing nothing", so a key
  // press never looks like it was silently swallowed.
  const [clipboardHint, setClipboardHint] = useState<string | null>(null);
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [contextMenu, setContextMenu] = useState<TerminalContextMenuState | null>(null);

  const showHint = useCallback((message: string | null) => {
    if (hintTimerRef.current) {
      clearTimeout(hintTimerRef.current);
      hintTimerRef.current = null;
    }
    setClipboardHint(message);
    if (message && typeof setTimeout === "function") {
      hintTimerRef.current = setTimeout(() => {
        hintTimerRef.current = null;
        setClipboardHint(null);
      }, CLIPBOARD_HINT_MS);
    }
  }, []);

  useEffect(
    () => () => {
      if (hintTimerRef.current) clearTimeout(hintTimerRef.current);
    },
    [],
  );

  const readSelection = useCallback((): string => {
    const term = termRef.current as ClipboardCapableTerm | null;
    return term?.getSelection?.() ?? "";
  }, [termRef]);

  const copySelection = useCallback(async () => {
    // An empty selection is a deliberate hinted no-op, never a fallthrough to
    // SIGINT: the interrupt gesture is gone, so "Ctrl+C on nothing" must not
    // reach the PTY. copyTextToClipboard() also refuses to overwrite the user's
    // clipboard with an empty string.
    const status = await copyTextToClipboard(readSelection());
    showHint(copyHint(status));
  }, [readSelection, showHint]);

  const pasteFromClipboard = useCallback(async () => {
    const { status, text } = await readTextFromClipboard();
    if (status === "ok") {
      const term = termRef.current as ClipboardCapableTerm | null;
      if (typeof term?.paste === "function") {
        // Route through xterm so the text takes exactly the path typed input
        // takes — including bracketed-paste framing, which TUIs such as
        // claude-code enable and rely on so a multi-line paste is not executed
        // line by line. xterm's paste() ends in the same onData handler that
        // forwards keystrokes as stdin frames.
        term.paste(text);
      } else {
        send({ type: "stdin", data: text });
      }
    }
    showHint(pasteHint(status));
  }, [send, showHint, termRef]);

  // The key handler is installed into xterm once, so it reads the current
  // callbacks through refs instead of capturing them.
  const copySelectionRef = useRef(copySelection);
  const pasteFromClipboardRef = useRef(pasteFromClipboard);
  copySelectionRef.current = copySelection;
  pasteFromClipboardRef.current = pasteFromClipboard;

  const handleTerminalKeyEvent = useCallback((ev: KeyboardEvent): boolean => {
    // xterm calls this for keydown/keypress/keyup; act once, on keydown.
    if (ev.type !== "keydown") return true;
    // Ctrl+Shift+C / Ctrl+Shift+V keep their conventional terminal meaning, and
    // Ctrl+T / Ctrl+W / Ctrl+1..9 belong to the TerminalTabs window-level
    // listener (which runs in the capture phase, so they never get here).
    if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return true;
    const key = ev.key?.toLowerCase();
    if (key === "c") {
      // preventDefault() suppresses the browser's own copy so the clipboard is
      // written exactly once, by us, from the xterm buffer selection.
      ev.preventDefault();
      void copySelectionRef.current();
      return false;
    }
    if (key === "v") {
      // Where the page cannot read the clipboard (Firefox, insecure origins),
      // stand aside: the browser's native paste is then the only working path,
      // and xterm already forwards it to stdin via its paste event. Claiming
      // the key here would take paste away entirely.
      if (!canReadClipboard()) return true;
      // preventDefault() suppresses that same native paste event — without it
      // the text would arrive twice, once from the browser and once from us.
      ev.preventDefault();
      void pasteFromClipboardRef.current();
      return false;
    }
    return true;
  }, []);

  const handleContextMenu = useCallback(
    (ev: React.MouseEvent<HTMLDivElement>) => {
      // Replace the browser menu (whose "Copy" cannot see the xterm buffer
      // selection) with one that can.
      ev.preventDefault();
      const term = termRef.current as ClipboardCapableTerm | null;
      const canCopy =
        typeof term?.hasSelection === "function" ? term.hasSelection() : readSelection().length > 0;
      const rect = frameRef.current?.getBoundingClientRect();
      setContextMenu({
        x: rect ? ev.clientX - rect.left : ev.clientX,
        y: rect ? ev.clientY - rect.top : ev.clientY,
        canCopy,
      });
    },
    [frameRef, readSelection, termRef],
  );

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  const handleMenuCopy = useCallback(() => {
    closeContextMenu();
    void copySelection();
  }, [closeContextMenu, copySelection]);

  const handleMenuPaste = useCallback(() => {
    closeContextMenu();
    void pasteFromClipboard();
  }, [closeContextMenu, pasteFromClipboard]);

  return {
    clipboardHint,
    contextMenu,
    handleContextMenu,
    closeContextMenu,
    handleMenuCopy,
    handleMenuPaste,
    handleTerminalKeyEvent,
  };
}
