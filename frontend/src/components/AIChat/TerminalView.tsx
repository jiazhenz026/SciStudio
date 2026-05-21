/**
 * ADR-034 Phase 1.3: TerminalView — xterm.js wrapper bound to a PTY WebSocket.
 *
 * - Creates a Terminal + FitAddon + SearchAddon + WebLinksAddon on mount.
 * - Opens a single WS for the tab's lifetime via usePtyWebSocket.
 * - Wires keystrokes -> stdin, server stdout -> term.write, exit/error ->
 *   callbacks bubbled up to TerminalTab.
 * - On container resize: fit() then send a `resize` frame with the new dims.
 *
 * UTF-8 strings flow over the WS in both directions (xterm.js write() and
 * onData() use strings, never Buffers — confirmed by xterm docs).
 */
import "@xterm/xterm/css/xterm.css";

import { useEffect, useRef } from "react";

import { usePtyWebSocket } from "./hooks/usePtyWebSocket";

export interface TerminalViewProps {
  tabId: string;
  projectDir: string;
  provider: "claude-code" | "codex";
  dangerous: boolean;
  onExit: (code: number) => void;
  onError: (message: string) => void;
}

export function TerminalView({
  tabId,
  projectDir,
  provider,
  dangerous,
  onExit,
  onError,
}: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // Keep mutable refs to the xterm objects + addons so the WS-message handler
  // closure can reach them without re-rendering.
  const termRef = useRef<unknown>(null);
  const fitRef = useRef<{ fit: () => void } | null>(null);
  // Buffer stdout that arrives before xterm finishes its async dynamic-import
  // bootstrap. Without this, the PTY's startup banner (claude-code prints
  // several KB immediately on spawn) gets silently dropped, leaving the TUI
  // mid-render with no prior screen state.
  const pendingWritesRef = useRef<string[]>([]);

  // Keep callbacks fresh without re-mounting the WS (which would tear down
  // the PTY subprocess).
  const onExitRef = useRef(onExit);
  const onErrorRef = useRef(onError);
  onExitRef.current = onExit;
  onErrorRef.current = onError;

  const { send } = usePtyWebSocket({
    tabId,
    projectDir,
    provider,
    dangerous,
    onMessage: (frame) => {
      if (frame.type === "stdout") {
        const t = termRef.current as { write?: (data: string) => void } | null;
        if (t?.write) {
          t.write(frame.data);
        } else {
          pendingWritesRef.current.push(frame.data);
        }
      } else if (frame.type === "exit") {
        onExitRef.current(frame.code);
      } else if (frame.type === "error") {
        onErrorRef.current(frame.message);
      }
    },
  });

  // Mount xterm.js on first render; tear it down on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let cancelled = false;
    let term: { write: (s: string) => void; onData: (cb: (s: string) => void) => { dispose: () => void }; open: (el: HTMLElement) => void; dispose: () => void; loadAddon: (a: unknown) => void; cols: number; rows: number } | null = null;
    let onDataDisposable: { dispose: () => void } | null = null;
    let resizeObserver: ResizeObserver | null = null;

    void (async () => {
      // Dynamic import so SSR / Vitest can mock the module without polluting
      // the JSDOM environment with canvas-heavy globals.
      const xtermMod = await import("@xterm/xterm");
      const fitMod = await import("@xterm/addon-fit");
      const searchMod = await import("@xterm/addon-search");
      const linksMod = await import("@xterm/addon-web-links");
      if (cancelled) return;

      const TerminalCtor = (xtermMod as { Terminal: new (opts?: unknown) => typeof term }).Terminal;
      const FitAddon = (fitMod as { FitAddon: new () => { fit: () => void } }).FitAddon;
      const SearchAddon = (searchMod as { SearchAddon: new () => unknown }).SearchAddon;
      const WebLinksAddon = (linksMod as { WebLinksAddon: new () => unknown }).WebLinksAddon;

      term = new TerminalCtor({
        // xterm's default ANSI black is #2e3436 — nearly invisible on the
        // #1e1e1e background. Codex occasionally emits ANSI color 0 (black)
        // for foreground text, which then renders as unreadable dark-on-dark.
        // Mirror the VS Code dark+ approach: brighten "black" to a readable
        // grey so colored output stays visible regardless of which palette
        // index the agent picks. Explicit foreground/cursor guarantees the
        // default text colour is the brighter one users expect.
        theme: {
          background: "#1e1e1e",
          foreground: "#e6e6e6",
          cursor: "#ffffff",
          cursorAccent: "#1e1e1e",
          black: "#666666",
          brightBlack: "#7f7f7f",
        },
        fontFamily: "Consolas, Menlo, monospace",
        fontSize: 14,
        cursorBlink: true,
        convertEol: true,
      }) as typeof term;

      const fit = new FitAddon();
      const search = new SearchAddon();
      const links = new WebLinksAddon();
      // Refs filled in for the onMessage closure.
      termRef.current = term;
      fitRef.current = fit;

      term!.loadAddon(fit);
      term!.loadAddon(search);
      term!.loadAddon(links);
      term!.open(container);
      try {
        fit.fit();
      } catch {
        // fit can throw if the container has zero dims; ignore — the resize
        // observer will fire once layout settles.
      }

      // Flush stdout that arrived during the async xterm bootstrap, then
      // notify the PTY of the post-fit viewport so subsequent output is
      // laid out against the real cols/rows rather than the 120x30 default.
      const pending = pendingWritesRef.current;
      if (pending.length > 0) {
        for (const chunk of pending) {
          term!.write(chunk);
        }
        pendingWritesRef.current = [];
      }
      if (term!.cols > 0 && term!.rows > 0) {
        send({ type: "resize", cols: term!.cols, rows: term!.rows });
      }

      onDataDisposable = term!.onData((data: string) => {
        send({ type: "stdin", data });
      });

      // Watch container size; on resize, fit() then notify the PTY.
      // The first fire happens shortly after observe() with the initial
      // size, which is what we want.
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
          try {
            fit.fit();
            if (term && term.cols > 0 && term.rows > 0) {
              send({ type: "resize", cols: term.cols, rows: term.rows });
            }
          } catch {
            // Ignore transient layout glitches.
          }
        });
        resizeObserver.observe(container);
      }
    })();

    return () => {
      cancelled = true;
      try {
        onDataDisposable?.dispose();
      } catch {
        /* ignore */
      }
      try {
        resizeObserver?.disconnect();
      } catch {
        /* ignore */
      }
      try {
        term?.dispose();
      } catch {
        /* ignore */
      }
      termRef.current = null;
      fitRef.current = null;
    };
    // Intentionally no deps — the props that change WS identity also tear
    // down this component (TerminalTab unmounts the view on exit/reopen).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="flex h-full flex-col overflow-hidden rounded-2xl border border-stone-200 bg-[#1e1e1e]"
      data-testid={`terminal-view-${tabId}`}
    >
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden"
        // Padding on the xterm host: keep some breathing room from the
        // bordered corners.
        style={{ padding: 4 }}
      />
    </div>
  );
}
