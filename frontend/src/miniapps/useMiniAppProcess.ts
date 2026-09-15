/**
 * ADR-054 FR-015 — the MiniApp tab's view of its process.
 *
 * The state and the resident memory are refreshed at least every five seconds
 * while the tab is mounted. A MiniApp whose panel carries no `panel.py` has no
 * process at all and the route answers 404 `no_process`: that is a legitimate
 * MiniApp, not an error, so the poll stops and the toolbar shows nothing
 * rather than an alarm.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../lib/api/core";
import { panelsApi } from "../lib/api/panels";
import type { PanelProcessStatus } from "../panels/types";

/** FR-015 — at least every five seconds. */
export const MINIAPP_PROCESS_POLL_MS = 5000;

export interface MiniAppProcessState {
  /** The last status seen, or `null` before the first answer. */
  status: PanelProcessStatus | null;
  /** True once the context reported it has no process; the poll then stops. */
  absent: boolean;
  /** The last poll failure that was not a `no_process` 404. */
  error: string | null;
  /** Whether a Restart or Stop is in flight. */
  busy: boolean;
  restart: () => void;
  stop: () => void;
}

export function useMiniAppProcess(
  contextId: string | null,
  initial: PanelProcessStatus | null = null,
): MiniAppProcessState {
  const [status, setStatus] = useState<PanelProcessStatus | null>(initial);
  const [absent, setAbsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Read by the interval without re-arming it: a status answer must not
  // restart the five-second clock, or a slow backend drifts the cadence.
  const stopped = useRef(false);
  const revision = useRef(0);
  const actionPending = useRef(false);

  useEffect(() => {
    revision.current += 1;
    actionPending.current = false;
    setBusy(false);
    stopped.current = false;
    setAbsent(false);
    setError(null);
    if (!contextId) {
      setStatus(null);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    let pendingPoll: number | null = null;
    const poll = () => {
      if (cancelled || stopped.current || actionPending.current || pendingPoll === revision.current)
        return;
      const request = ++revision.current;
      pendingPoll = request;
      void panelsApi
        .processStatus(contextId, controller.signal)
        .then((next) => {
          if (cancelled || request !== revision.current) return;
          setStatus(next);
          setError(null);
        })
        .catch((err: unknown) => {
          if (cancelled || request !== revision.current) return;
          // 404 `no_process`: this MiniApp has no panel.py. Nothing to poll.
          if (err instanceof ApiError && err.status === 404) {
            stopped.current = true;
            setAbsent(true);
            setStatus(null);
            return;
          }
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          if (pendingPoll === request) pendingPoll = null;
        });
    };
    poll();
    const timer = setInterval(poll, MINIAPP_PROCESS_POLL_MS);
    return () => {
      cancelled = true;
      revision.current += 1;
      clearInterval(timer);
      controller.abort();
    };
  }, [contextId]);

  const act = useCallback(
    (run: (id: string) => Promise<{ process?: PanelProcessStatus | null }>) => {
      if (!contextId || actionPending.current) return;
      // Ignore reads begun before the command, and pause polling until it settles.
      // The same revision invalidates command results when the context closes.
      const request = ++revision.current;
      actionPending.current = true;
      setBusy(true);
      void run(contextId)
        .then((context) => {
          if (request !== revision.current) return;
          stopped.current = false;
          setAbsent(false);
          setError(null);
          setStatus(context.process ?? null);
        })
        .catch((err: unknown) => {
          if (request !== revision.current) return;
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          if (request !== revision.current) return;
          actionPending.current = false;
          setBusy(false);
        });
    },
    [contextId],
  );

  return {
    status,
    absent,
    error,
    busy,
    // FR-014 — a new process for the same context and target.
    restart: useCallback(() => act((id) => panelsApi.restartProcess(id)), [act]),
    stop: useCallback(() => act((id) => panelsApi.stopProcess(id)), [act]),
  };
}
