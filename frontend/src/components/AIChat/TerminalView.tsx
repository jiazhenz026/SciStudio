/**
 * ADR-034 Phase 1.3: TerminalView — xterm.js wrapper bound to a PTY WebSocket.
 *
 * - Creates a Terminal + FitAddon + SearchAddon + WebLinksAddon on mount.
 * - Opens a single WS for the tab's lifetime via usePtyWebSocket.
 * - Wires keystrokes -> stdin, server stdout -> term.write, exit/error ->
 *   callbacks bubbled up to TerminalTab.
 *
 * Renderer: xterm's default DOM renderer. #1320 had switched to
 * @xterm/addon-canvas to fix scroll ghosting, but the canvas renderer
 * (deprecated upstream) does not repaint cleanly when the PTY viewport is
 * resized — it left claude-code's "thinking" spinner invisible mid-drag and
 * stamped stale horizontal rules across the buffer. Reverted to the DOM
 * renderer, which reflows natively on resize. Its one weakness — only "dirty"
 * cells repaint, so scrolling / re-showing leaves ghosted glyphs — is countered
 * with an explicit refresh() on the onScroll and return-to-view paths below.
 *
 * Resize policy: freeze the terminal during a bottom-panel drag and refit ONCE
 * when it settles (RESIZE_DEBOUNCE_MS). Refitting on every drag frame churns
 * the PTY viewport and makes the TUI repaint continuously; one fit + SIGWINCH
 * on the settled size lets it repaint cleanly a single time.
 *
 * Resize delivery: for the TUI to actually reflow on that SIGWINCH the agent
 * must own the slave PTY as its controlling terminal — otherwise the kernel has
 * no foreground process group to signal and the agent stays stuck at its
 * spawn-time size (the root cause of #1946 fullscreen-mode ghosting). That fix
 * lives in the backend spawn (src/scistudio/ai/agent/terminal.py), not here.
 *
 * Known upstream limitation (NOT a SciStudio bug): claude-code leaves ghosted
 * horizontal rules and drops its "thinking" spinner when its window is resized
 * mid-stream. This reproduces in a plain macOS terminal (Terminal.app / iTerm)
 * and does NOT happen with codex in this same component — it is claude-code's
 * own SIGWINCH redraw behaviour, which we cannot fix from the host terminal.
 * See #1711. The manual refresh (↻) button gives the user an explicit escape
 * hatch to force a host-side redraw when that upstream residue appears.
 *
 * UTF-8 strings flow over the WS in both directions (xterm.js write() and
 * onData() use strings, never Buffers — confirmed by xterm docs).
 */
import "@xterm/xterm/css/xterm.css";

import { useCallback, useEffect, useRef, useState } from "react";

import type { TerminalProvider } from "../../store/types";
import { usePtyWebSocket } from "./hooks/usePtyWebSocket";

// Idle delay after the last ResizeObserver callback before we refit + notify the
// PTY. Long enough that dragging the bottom-panel splitter does not refit on
// every frame, short enough to feel responsive once the drag stops.
const RESIZE_DEBOUNCE_MS = 100;

export interface TerminalViewProps {
  tabId: string;
  projectDir: string;
  provider: TerminalProvider;
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
  const [initialSize, setInitialSize] = useState<{ cols: number; rows: number } | null>(null);
  const ptyOpenRef = useRef(false);
  const lastSentResizeRef = useRef<{ cols: number; rows: number } | null>(null);
  // Buffer stdout that arrives before xterm finishes its async dynamic-import
  // bootstrap. Without this, the PTY's startup banner (claude-code prints
  // several KB immediately on spawn) gets silently dropped, leaving the TUI
  // mid-render with no prior screen state.
  const pendingWritesRef = useRef<string[]>([]);
  const sawExitRef = useRef(false);

  // Keep callbacks fresh without re-mounting the WS (which would tear down
  // the PTY subprocess).
  const onExitRef = useRef(onExit);
  const onErrorRef = useRef(onError);
  onExitRef.current = onExit;
  onErrorRef.current = onError;

  useEffect(() => {
    sawExitRef.current = false;
    ptyOpenRef.current = false;
    lastSentResizeRef.current = null;
    setInitialSize(null);
  }, [tabId, projectDir, provider, dangerous]);

  const { send } = usePtyWebSocket({
    tabId,
    projectDir,
    provider,
    dangerous,
    enabled: initialSize !== null,
    initialCols: initialSize?.cols ?? null,
    initialRows: initialSize?.rows ?? null,
    onMessage: (frame) => {
      if (frame.type === "stdout") {
        const t = termRef.current as { write?: (data: string) => void } | null;
        if (t?.write) {
          t.write(frame.data);
        } else {
          pendingWritesRef.current.push(frame.data);
        }
      } else if (frame.type === "exit") {
        sawExitRef.current = true;
        onExitRef.current(frame.code);
      } else if (frame.type === "error") {
        onErrorRef.current(frame.message);
      }
    },
    onOpen: () => {
      ptyOpenRef.current = true;
    },
    onClose: (ev) => {
      ptyOpenRef.current = false;
      if (sawExitRef.current) {
        return;
      }
      const reason = ev.reason ? `: ${ev.reason}` : "";
      onErrorRef.current(`WebSocket closed before PTY exit (code ${ev.code}${reason})`);
    },
  });

  // Mount xterm.js on first render; tear it down on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let cancelled = false;
    let term: {
      write: (s: string) => void;
      onData: (cb: (s: string) => void) => { dispose: () => void };
      onScroll: (cb: (ydisp: number) => void) => { dispose: () => void };
      open: (el: HTMLElement) => void;
      dispose: () => void;
      loadAddon: (a: unknown) => void;
      refresh: (start: number, end: number) => void;
      cols: number;
      rows: number;
    } | null = null;
    let onDataDisposable: { dispose: () => void } | null = null;
    let onScrollDisposable: { dispose: () => void } | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let intersectionObserver: IntersectionObserver | null = null;
    // Debounce handle that freezes the terminal while the bottom-panel splitter
    // is dragged and refits once the drag settles. Cleared on unmount so the
    // callback never touches a disposed terminal.
    let resizeDebounce: ReturnType<typeof setTimeout> | null = null;

    const rememberInitialSize = () => {
      if (!term || term.cols <= 0 || term.rows <= 0) return;
      const next = { cols: term.cols, rows: term.rows };
      lastSentResizeRef.current = next;
      setInitialSize(next);
    };

    const sendResizeIfChanged = () => {
      if (!ptyOpenRef.current || !term || term.cols <= 0 || term.rows <= 0) return;
      const previous = lastSentResizeRef.current;
      if (previous?.cols === term.cols && previous.rows === term.rows) return;
      const next = { cols: term.cols, rows: term.rows };
      lastSentResizeRef.current = next;
      send({ type: "resize", cols: next.cols, rows: next.rows });
    };

    // Force a full repaint of the visible rows. Safe whenever the screen buffer
    // is current (scroll / return-to-view) — it is NOT used on resize, where the
    // buffer is mid-update and repainting from it would stamp stale content.
    const repaintVisible = () => {
      if (cancelled || !term) return;
      try {
        term.refresh(0, Math.max(0, term.rows - 1));
      } catch {
        // Ignore transient layout glitches.
      }
    };

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
        // PTY-backed TUIs own their cursor movement and redraw protocol.
        // Converting LF to CRLF is useful for plain logs, but it corrupts
        // full-screen redraws such as Claude Code's startup/status repaint.
        convertEol: false,
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
      // Default DOM renderer (no @xterm/addon-canvas) — see file header.
      term!.open(container);
      try {
        fit.fit();
      } catch {
        // fit can throw if the container has zero dims; ignore — the resize
        // observer will fire once layout settles.
      }
      rememberInitialSize();

      // Flush stdout that arrived during the async xterm bootstrap.
      // Normally there is none now: the PTY WebSocket waits for initialSize
      // so the backend can spawn the process at the fitted viewport.
      const pending = pendingWritesRef.current;
      if (pending.length > 0) {
        for (const chunk of pending) {
          term!.write(chunk);
        }
        pendingWritesRef.current = [];
      }

      onDataDisposable = term!.onData((data: string) => {
        send({ type: "stdin", data });
      });

      // DOM renderer only repaints "dirty" cells, so dragging the scrollbar
      // over a TUI leaves ghosted glyphs (the #1320 symptom the canvas renderer
      // used to hide). Force a full repaint on every scroll. Safe: scrolling
      // does not change the buffer. A pending flag coalesces the burst to one
      // refresh per frame.
      let scrollRefreshScheduled = false;
      onScrollDisposable = term!.onScroll(() => {
        if (cancelled || !term || scrollRefreshScheduled) return;
        scrollRefreshScheduled = true;
        const run = () => {
          scrollRefreshScheduled = false;
          repaintVisible();
        };
        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(run);
        } else {
          run();
        }
      });

      // Refit to the settled container size, then notify the PTY. fit() reflows
      // the DOM renderer; the TUI repaints itself in response to the SIGWINCH.
      // No refresh() here — at this instant the buffer is mid-update.
      const refit = () => {
        if (cancelled || !term) return;
        try {
          fit.fit();
          if (!lastSentResizeRef.current) {
            rememberInitialSize();
          } else {
            sendResizeIfChanged();
          }
        } catch {
          // Ignore transient zero-size layout frames.
        }
      };

      // Freeze during the drag, refit once it settles.
      const scheduleRefit = () => {
        if (resizeDebounce) clearTimeout(resizeDebounce);
        if (typeof setTimeout === "function") {
          resizeDebounce = setTimeout(() => {
            resizeDebounce = null;
            refit();
          }, RESIZE_DEBOUNCE_MS);
        } else {
          refit();
        }
      };

      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
          scheduleRefit();
        });
        resizeObserver.observe(container);
      }

      // Repaint when the terminal returns to view. The bottom panel hides
      // inactive surfaces with `display:none` (so PTY subprocesses survive);
      // while hidden the container has zero size and ResizeObserver does not
      // fire, and the DOM renderer does not repaint. On re-show, refit (size may
      // have changed while hidden) and force a full repaint so the user never
      // sees a stale / blank frame (bug#8).
      if (typeof IntersectionObserver !== "undefined") {
        let wasVisible = true;
        intersectionObserver = new IntersectionObserver((entries) => {
          const entry = entries[0];
          if (!entry) return;
          if (entry.isIntersecting && !wasVisible) {
            wasVisible = true;
            if (cancelled || !term) return;
            try {
              fit.fit();
              sendResizeIfChanged();
            } catch {
              // Ignore transient layout glitches.
            }
            repaintVisible();
          } else if (!entry.isIntersecting) {
            wasVisible = false;
          }
        });
        intersectionObserver.observe(container);
      }
    })();

    return () => {
      cancelled = true;
      if (resizeDebounce) {
        clearTimeout(resizeDebounce);
        resizeDebounce = null;
      }
      try {
        onDataDisposable?.dispose();
      } catch {
        /* ignore */
      }
      try {
        onScrollDisposable?.dispose();
      } catch {
        /* ignore */
      }
      try {
        resizeObserver?.disconnect();
      } catch {
        /* ignore */
      }
      try {
        intersectionObserver?.disconnect();
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

  // Manual escape hatch (#1946): "unstick" a garbled / ghosted terminal without
  // tearing down the PTY (a full renderer reload would drop the running agent
  // session). The stuck-size root cause is fixed in the backend PTY spawn (the
  // agent now owns a controlling terminal, so SIGWINCH reaches it). This button
  // is a belt-and-braces host-side redraw for the residual case where the agent
  // leaves its own paint artifacts (a known upstream claude-code limitation,
  // #1711): drop the container out of layout, force a synchronous reflow so its
  // paint records are discarded, restore it, then repaint the rows from the
  // (correct) buffer — the programmatic equivalent of selecting the text.
  const handleRefresh = useCallback(() => {
    const term = termRef.current as {
      refresh?: (start: number, end: number) => void;
      rows: number;
    } | null;
    const container = containerRef.current;
    if (container) {
      const previousDisplay = container.style.display;
      container.style.display = "none";
      // Read a layout property to force the hide to flush before we restore it;
      // toggling display in one synchronous pass would otherwise coalesce and
      // never repaint.
      void container.offsetHeight;
      container.style.display = previousDisplay;
    }
    try {
      fitRef.current?.fit();
      term?.refresh?.(0, Math.max(0, term.rows - 1));
    } catch {
      // Ignore transient layout glitches.
    }
  }, []);

  return (
    <div
      className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-stone-200 bg-[#1e1e1e]"
      data-testid={`terminal-view-${tabId}`}
    >
      <button
        type="button"
        onClick={handleRefresh}
        title="Refresh display — redraw the terminal if the screen looks garbled or ghosted"
        aria-label="Refresh terminal display"
        data-testid={`terminal-refresh-${tabId}`}
        className="absolute right-2 top-2 z-50 rounded-md border border-white/10 bg-white/10 px-2 py-1 text-xs leading-none text-stone-300 opacity-60 transition hover:bg-white/20 hover:opacity-100"
      >
        ↻
      </button>
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
