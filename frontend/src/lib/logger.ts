/**
 * Frontend logging (#1741).
 *
 * A tiny logger that:
 *  - writes to the browser console (human-readable),
 *  - keeps a bounded in-memory ring buffer for export,
 *  - batches records at/above a reflux threshold to the backend
 *    (`POST /api/client-logs`) so a beta tester's frontend errors land on disk
 *    where developers can see them — no third-party telemetry.
 *
 * Use `logger.{debug,info,warn,error}` at user-action and API boundaries. The
 * global error handlers and the React ErrorBoundary route uncaught failures
 * here too, so the frontend is no longer an observability black hole.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface ClientLogRecord {
  level: LogLevel;
  message: string;
  ts: string;
  url?: string;
  request_id?: string;
  context?: Record<string, unknown>;
}

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

const RING_LIMIT = 500;
const REFLUX_THRESHOLD: LogLevel = "warn"; // reflux warn + error to the backend
const FLUSH_INTERVAL_MS = 4000;
const MAX_BATCH = 50;

const ring: ClientLogRecord[] = [];
let pending: ClientLogRecord[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function nowIso(): string {
  return new Date().toISOString();
}

function pushRing(record: ClientLogRecord): void {
  ring.push(record);
  if (ring.length > RING_LIMIT) {
    ring.splice(0, ring.length - RING_LIMIT);
  }
}

function scheduleFlush(): void {
  if (flushTimer === null) {
    flushTimer = setTimeout(() => void flush(), FLUSH_INTERVAL_MS);
  }
}

async function flush(): Promise<void> {
  flushTimer = null;
  if (pending.length === 0) return;
  const batch = pending.slice(0, MAX_BATCH);
  pending = pending.slice(MAX_BATCH);
  try {
    await fetch("/api/client-logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ records: batch }),
      keepalive: true,
    });
  } catch {
    // Backend unreachable; the records remain in the ring buffer so the
    // "Export logs" button can still ship them.
  }
  if (pending.length > 0) scheduleFlush();
}

function emit(level: LogLevel, message: string, context?: Record<string, unknown>): void {
  const record: ClientLogRecord = {
    level,
    message,
    ts: nowIso(),
    url: typeof window !== "undefined" ? window.location?.href : undefined,
    request_id: typeof context?.request_id === "string" ? context.request_id : undefined,
    context,
  };
  pushRing(record);

  // eslint-disable-next-line no-console -- this IS the console logging boundary
  const sink =
    level === "error"
      ? console.error
      : level === "warn"
        ? console.warn
        : level === "debug"
          ? console.debug
          : console.info;
  sink(`[scistudio] ${message}`, context ?? "");

  if (LEVEL_ORDER[level] >= LEVEL_ORDER[REFLUX_THRESHOLD]) {
    pending.push(record);
    scheduleFlush();
  }
}

export const logger = {
  debug: (message: string, context?: Record<string, unknown>) => emit("debug", message, context),
  info: (message: string, context?: Record<string, unknown>) => emit("info", message, context),
  warn: (message: string, context?: Record<string, unknown>) => emit("warn", message, context),
  error: (message: string, context?: Record<string, unknown>) => emit("error", message, context),
};

/** Return a copy of the in-memory ring buffer (for export / debugging). */
export function getLogBuffer(): ClientLogRecord[] {
  return [...ring];
}

/** Install global `error` / `unhandledrejection` handlers + a flush-on-unload. */
export function installGlobalErrorHandlers(): void {
  if (typeof window === "undefined") return;
  window.addEventListener("error", (event) => {
    logger.error(`uncaught error: ${event.message}`, {
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      stack: event.error?.stack,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason as { message?: string; stack?: string } | undefined;
    logger.error(`unhandled rejection: ${reason?.message ?? String(event.reason)}`, {
      stack: reason?.stack,
    });
  });
  window.addEventListener("beforeunload", () => void flush());
}

/** Download a backend diagnostic bundle (logs + environment + run logs) as a zip. */
export async function exportDiagnosticBundle(): Promise<void> {
  try {
    const response = await fetch("/api/diagnostics/bundle");
    if (!response.ok) throw new Error(`bundle request failed: ${response.status}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "scistudio-diagnostics.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    logger.info("diagnostic bundle exported");
  } catch (error) {
    logger.error(`diagnostic bundle export failed: ${String(error)}`);
  }
}
