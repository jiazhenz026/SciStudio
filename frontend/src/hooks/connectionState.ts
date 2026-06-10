/**
 * Shared connection-state primitives for the realtime hooks
 * (``useSSE`` / ``useWebSocket``).
 *
 * #177: neither hook reconnected after a dropped connection, silently
 * stopping all updates. This module centralizes the reconnection
 * backoff schedule and the connection-status vocabulary so both hooks
 * behave identically and the UI can reflect disconnect/reconnect.
 *
 * The status is intentionally derived in the React hooks (component
 * state); it is NOT runtime truth and is never persisted to the store
 * as durable data. It exists only so the toolbar can render a live
 * indicator.
 */

/** Exponential-backoff schedule shared by both realtime hooks (#177). */
export const RECONNECT_INITIAL_DELAY_MS = 1000;
export const RECONNECT_MAX_DELAY_MS = 30000;
export const RECONNECT_BACKOFF_FACTOR = 2;

/**
 * Connection lifecycle as surfaced to the UI.
 *
 * - ``connecting``    — first attempt, no successful open yet.
 * - ``connected``     — socket/EventSource is open.
 * - ``reconnecting``  — connection dropped; a retry is scheduled or in
 *                       flight (exponential backoff).
 * - ``disconnected``  — hook disabled / torn down; no retry pending.
 */
export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

/**
 * Compute the next backoff delay, capped at
 * :data:`RECONNECT_MAX_DELAY_MS`.
 */
export function nextBackoffDelay(currentDelay: number): number {
  return Math.min(currentDelay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY_MS);
}
