/**
 * ADR-054 spec 4 (T-013) — the toolbar's collapsible kernel list (FR-014's
 * share, FR-015, FR-016's restart).
 *
 * The list is project-wide, not tab-wide: FR-015 asks for *every* live kernel
 * in the project with its session and its memory, which is what
 * `GET /api/explore/kernels` answers. So this component reads the slice
 * directly rather than taking the session it is rendered beside.
 *
 * **Two sources, and the events win.** The list response names every kernel
 * the service can see; the `explore.kernel_state` events are what move a row
 * afterwards. `buildKernelRows` merges them, and where a session has had an
 * event applied that event's state, pid and memory are what the row shows —
 * so ending a kernel moves the list when the runtime says it moved, not when
 * the button was pressed. That is FR-034 in the shape this list takes it: the
 * end control sends the command and writes nothing.
 *
 * **A retired kernel is not in the response.**
 * `ExploreSessionService.kernels()` keeps only `starting`, `idle` and `busy`,
 * so a kernel that died or was retired by a branch change has already left the
 * list by the time the person could ask about it. FR-016's "offer restart when
 * the runtime reports the kernel dead or retired" therefore cannot be served
 * from the response at all, and is served from the session's own kernel view —
 * which is written from the kernel-state event and from the session response,
 * both of which do carry `needs_restart`.
 *
 * TODO(#2253): a session this browser never opened has neither a listing nor a
 *   session view once its kernel retires, so its row is in neither source; and
 *   the list does not poll, so a kernel started elsewhere appears only on the
 *   next fetch.
 *   Out of scope per the ADR-054 assembly dispatch: the first needs
 *   `needs_restart` on `KernelListItem` (a `src/scistudio/**` change), and the
 *   second is a refresh policy spec 4 does not state.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `F-A4-004`,
 *   `F-A4-005`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { exploreApi } from "../lib/api/explore";
import { useAppStore } from "../store";
import type { ExploreSessionState } from "../store/types";
import type { ExploreKernelListItem } from "../types/api";

/** One row of the list, after the response and the events are merged. */
export interface KernelRow {
  sessionId: string;
  notebookPath: string;
  state: string;
  pid: number | null;
  memoryBytes: number | null;
  pythonExecutable: string | null;
  /** The runtime reported this session's kernel retired or dead (FR-016). */
  needsRestart: boolean;
}

/** The kernel states the service's own list is built from. */
const LIVE_STATES: readonly string[] = ["starting", "idle", "busy"];

/**
 * `true` when this session's kernel view is a statement rather than a default.
 *
 * `emptySession` starts every session at `not-started`, and a session response
 * leaves it there when it reports no kernel — so "not-started" alone cannot be
 * read as "the runtime said the kernel is gone". `lastEventAt` is set only by a
 * kernel-state event, and `needsRestart` only by an event or a session
 * response; either of them makes the view something the runtime said.
 */
function isStated(session: ExploreSessionState): boolean {
  return session.kernel.lastEventAt !== null || session.kernel.needsRestart;
}

/**
 * Merge the kernel list response with the per-session kernel views.
 *
 * Exported so the merge rules can be asserted without a store or a fetch.
 */
export function buildKernelRows(
  listed: readonly ExploreKernelListItem[],
  sessions: Record<string, ExploreSessionState>,
): KernelRow[] {
  const bySessionId = new Map<string, ExploreSessionState>();
  for (const session of Object.values(sessions)) {
    if (session.sessionId) bySessionId.set(session.sessionId, session);
  }

  const rows: KernelRow[] = [];
  const covered = new Set<string>();

  for (const item of listed) {
    covered.add(item.session_id);
    const session = bySessionId.get(item.session_id);
    const stated = session ? isStated(session) : false;
    const state = stated && session ? session.kernel.state : item.state;
    const needsRestart = session ? session.kernel.needsRestart : false;
    // The event retired it: the response is the older of the two statements,
    // so the row goes rather than lingering until the next fetch.
    if (stated && !LIVE_STATES.includes(state) && !needsRestart) continue;
    rows.push({
      sessionId: item.session_id,
      notebookPath: session?.notebookPath ?? item.notebook_path,
      state,
      pid: stated && session ? session.kernel.pid : item.pid,
      memoryBytes: stated && session ? session.kernel.memoryBytes : item.memory_bytes,
      pythonExecutable: item.python_executable,
      needsRestart,
    });
  }

  // Sessions the response does not carry: a kernel started since the last
  // fetch, and — the case FR-016 needs — one the runtime retired.
  for (const session of bySessionId.values()) {
    if (covered.has(session.sessionId)) continue;
    if (!isStated(session)) continue;
    if (!session.kernel.needsRestart && !LIVE_STATES.includes(session.kernel.state)) continue;
    rows.push({
      sessionId: session.sessionId,
      notebookPath: session.notebookPath,
      state: session.kernel.state,
      pid: session.kernel.pid,
      memoryBytes: session.kernel.memoryBytes,
      pythonExecutable: null,
      needsRestart: session.kernel.needsRestart,
    });
  }

  rows.sort((left, right) =>
    left.notebookPath === right.notebookPath
      ? left.sessionId.localeCompare(right.sessionId)
      : left.notebookPath.localeCompare(right.notebookPath),
  );
  return rows;
}

/** Memory as a person reads it. `null` is "the runtime reported none". */
export function formatMemory(bytes: number | null): string {
  if (bytes === null || Number.isNaN(bytes)) return "—";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

/** The last path segment, which is what names a session on a narrow toolbar. */
function basename(path: string): string {
  const cut = path.lastIndexOf("/");
  return cut === -1 ? path : path.slice(cut + 1);
}

/** The collapsible kernel list on the session toolbar. */
export function KernelList() {
  const kernels = useAppStore((state) => state.exploreKernels);
  const sessions = useAppStore((state) => state.sessions);
  const applyExploreKernelList = useAppStore((state) => state.applyExploreKernelList);

  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<readonly string[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await exploreApi.listExploreKernels();
      applyExploreKernelList(response.kernels);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, [applyExploreKernelList]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  const rows = useMemo(() => buildKernelRows(kernels, sessions), [kernels, sessions]);

  const send = useCallback(async (sessionId: string, command: () => Promise<unknown>) => {
    setPending((held) => [...held, sessionId]);
    setError(null);
    try {
      await command();
      // Deliberately nothing else. The row moves when the kernel-state event
      // arrives; writing the command's own response here would be the shell
      // reporting its wish rather than the runtime's answer (FR-034).
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending((held) => held.filter((id) => id !== sessionId));
    }
  }, []);

  return (
    <span className="relative inline-flex items-center">
      <button
        aria-expanded={open}
        className="toolbar-button"
        data-testid="explore-kernel-list-toggle"
        onClick={() => setOpen((held) => !held)}
        type="button"
      >
        Kernels ({rows.length})
      </button>

      {open ? (
        <div
          className="absolute top-full z-30 mt-1 w-[24rem] rounded-lg border border-stone-300 bg-white p-2 shadow-panel"
          data-testid="explore-kernel-list"
        >
          <div className="flex items-center justify-between px-1 pb-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
              Kernels
            </p>
            <button
              className="toolbar-button"
              data-testid="explore-kernel-list-refresh"
              disabled={loading}
              onClick={() => void refresh()}
              type="button"
            >
              {loading ? "…" : "Refresh"}
            </button>
          </div>

          {rows.length === 0 ? (
            <p className="px-1 text-[11px] text-stone-500" data-testid="explore-kernel-list-empty">
              No kernel is running in this project.
            </p>
          ) : null}

          <ul className="space-y-1">
            {rows.map((row) => {
              const busy = pending.includes(row.sessionId);
              const offerRestart = row.needsRestart || row.state === "dead";
              return (
                <li
                  className="flex items-center gap-2 rounded border border-stone-200 px-2 py-1"
                  data-kernel-state={row.state}
                  data-needs-restart={row.needsRestart ? "true" : "false"}
                  data-testid={`explore-kernel-row-${row.sessionId}`}
                  key={row.sessionId}
                >
                  <span className="min-w-0 flex-1">
                    <span
                      className="block truncate text-[11px] text-ink"
                      title={row.notebookPath}
                      data-testid="explore-kernel-row-session"
                    >
                      {basename(row.notebookPath)}
                    </span>
                    <span className="block text-[10px] text-stone-500">
                      {row.state}
                      {row.pid === null ? "" : ` · pid ${row.pid}`}
                    </span>
                  </span>
                  <span
                    className="w-16 shrink-0 text-right font-mono text-[11px] text-stone-600"
                    data-testid="explore-kernel-row-memory"
                  >
                    {formatMemory(row.memoryBytes)}
                  </span>
                  {offerRestart ? (
                    <button
                      className="toolbar-button"
                      data-testid={`explore-kernel-restart-${row.sessionId}`}
                      disabled={busy}
                      onClick={() =>
                        void send(row.sessionId, () =>
                          exploreApi.restartExploreSession(row.sessionId),
                        )
                      }
                      type="button"
                    >
                      Restart
                    </button>
                  ) : (
                    <button
                      className="toolbar-button"
                      data-testid={`explore-kernel-end-${row.sessionId}`}
                      disabled={busy}
                      onClick={() =>
                        void send(row.sessionId, () => exploreApi.endExploreKernel(row.sessionId))
                      }
                      type="button"
                    >
                      End
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          {error ? (
            <p
              className="mt-1 px-1 text-[11px] text-red-700"
              data-testid="explore-kernel-list-error"
            >
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </span>
  );
}
