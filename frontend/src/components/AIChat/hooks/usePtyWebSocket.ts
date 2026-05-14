/**
 * ADR-034 Phase 1.3: WebSocket hook for the PTY-backed embedded terminal.
 *
 * Protocol (LOCKED — backend uses the same spec):
 *   URL: ws://host/api/ai/pty/{tab_id}
 *          ?project_dir=<urlencoded_abs_path>
 *          &provider=<claude-code|codex>
 *          &dangerous=<true|false>
 *
 *   Client -> Server (JSON, one frame per WS message):
 *     {type: "stdin", data: "<utf-8 string>"}
 *     {type: "resize", cols: <int>, rows: <int>}
 *
 *   Server -> Client (JSON):
 *     {type: "stdout", data: "<utf-8 string>"}
 *     {type: "exit", code: <int>}
 *     {type: "error", message: "<string>"}
 *
 * No auto-reconnect. PTY exit is terminal; the frontend exposes a Reopen
 * button that re-mounts this hook with fresh params.
 */
import { useCallback, useEffect, useRef } from "react";

export type PtyClientFrame =
  | { type: "stdin"; data: string }
  | { type: "resize"; cols: number; rows: number };

export type PtyServerFrame =
  | { type: "stdout"; data: string }
  | { type: "exit"; code: number }
  | { type: "error"; message: string };

export interface UsePtyWebSocketParams {
  tabId: string;
  projectDir: string | null;
  provider: "claude-code" | "codex";
  dangerous: boolean;
  /** Called for each parsed server-side frame. */
  onMessage: (frame: PtyServerFrame) => void;
  /** Called once when the underlying socket opens. */
  onOpen?: () => void;
  /** Called if the WS closes unexpectedly (before an `exit` frame). */
  onClose?: (ev: CloseEvent) => void;
}

export interface UsePtyWebSocketResult {
  send: (frame: PtyClientFrame) => void;
  /** True while the WS is in OPEN state. */
  readonly readyStateRef: React.MutableRefObject<number>;
}

/** Build the PTY WS URL with all required query params, properly encoded. */
export function buildPtyUrl({
  tabId,
  projectDir,
  provider,
  dangerous,
  baseOrigin,
}: {
  tabId: string;
  projectDir: string;
  provider: string;
  dangerous: boolean;
  baseOrigin?: string;
}): string {
  // Derive ws:// or wss:// from window.location.protocol; in tests fall back
  // to ws://localhost. baseOrigin override is for unit tests.
  let origin = baseOrigin;
  if (!origin && typeof window !== "undefined" && window.location) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    origin = `${proto}//${window.location.host}`;
  }
  if (!origin) origin = "ws://localhost";

  const params = new URLSearchParams({
    project_dir: projectDir,
    provider,
    dangerous: dangerous ? "true" : "false",
  });
  return `${origin}/api/ai/pty/${encodeURIComponent(tabId)}?${params.toString()}`;
}

/**
 * Open and manage a single PTY WebSocket for the lifetime of the calling
 * component. The hook opens the socket on mount and closes it on unmount.
 *
 * If `projectDir` is null the hook does NOT open a socket (caller is in a
 * state where it cannot launch). When params change identity, the hook
 * closes the old socket and opens a new one — caller is responsible for
 * not flipping params during a live session.
 */
export function usePtyWebSocket(params: UsePtyWebSocketParams): UsePtyWebSocketResult {
  const { tabId, projectDir, provider, dangerous, onMessage, onOpen, onClose } = params;

  const wsRef = useRef<WebSocket | null>(null);
  const readyStateRef = useRef<number>(WebSocket.CLOSED);
  // Keep callbacks in refs so identity changes do not force WS reconnection.
  const onMessageRef = useRef(onMessage);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  onMessageRef.current = onMessage;
  onOpenRef.current = onOpen;
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!projectDir) {
      // No working dir -> cannot launch a PTY. Caller is in setup or closed
      // state; do nothing.
      return undefined;
    }
    const url = buildPtyUrl({ tabId, projectDir, provider, dangerous });
    const ws = new WebSocket(url);
    wsRef.current = ws;
    readyStateRef.current = ws.readyState;

    ws.onopen = () => {
      readyStateRef.current = ws.readyState;
      onOpenRef.current?.();
    };
    ws.onmessage = (ev) => {
      // Server always sends JSON-encoded text frames. Anything else is a
      // protocol violation and surfaced as an error frame so the UI shows it.
      try {
        const data = typeof ev.data === "string" ? ev.data : "";
        if (!data) return;
        const frame = JSON.parse(data) as PtyServerFrame;
        onMessageRef.current(frame);
      } catch (err) {
        onMessageRef.current({
          type: "error",
          message: `Malformed server frame: ${(err as Error).message}`,
        });
      }
    };
    ws.onerror = () => {
      // The browser fires 'error' just before 'close'; report it as an error
      // frame so the terminal can surface it. The actual close handler will
      // also fire.
      onMessageRef.current({ type: "error", message: "WebSocket error" });
    };
    ws.onclose = (ev) => {
      readyStateRef.current = ws.readyState;
      onCloseRef.current?.(ev);
    };

    return () => {
      readyStateRef.current = WebSocket.CLOSING;
      try {
        ws.close();
      } catch {
        // Already closed.
      }
      wsRef.current = null;
    };
  }, [tabId, projectDir, provider, dangerous]);

  const send = useCallback((frame: PtyClientFrame) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Drop the frame silently — the upstream UI will recover on the next
      // PTY exit/error event. We never queue, to avoid replaying stale
      // keystrokes onto a reconnected PTY.
      return;
    }
    try {
      ws.send(JSON.stringify(frame));
    } catch {
      // Buffer overflow or socket closed mid-send; ignore.
    }
  }, []);

  return { send, readyStateRef };
}
