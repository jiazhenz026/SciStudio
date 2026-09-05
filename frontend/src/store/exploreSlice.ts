/**
 * ADR-054 spec 4 (T-001) — the Explore session slice (FR-033, FR-034, FR-035).
 *
 * One place holds every open session's state, keyed by notebook path, and it
 * is written from exactly two sources: the responses of the routes in
 * `lib/api/explore.ts`, and the `explore.*` events that arrive on the
 * WebSocket the workflow already uses.
 *
 * **FR-034 is the rule this module exists to keep.** There is no code here
 * that computes a mark, a kernel state, or a binding. A mark is copied out of
 * the runtime's `marks` map; a kernel state is copied out of a `kernel_state`
 * event; a binding's `live` is `exists_in_kernel` copied. A command is never
 * reflected before its event arrives — `runCell` writes nothing, and the cell
 * turns `running` when the runtime says it did.
 *
 * **Ordering.** ADR-054 spec 3 publishes a session event on whichever thread
 * did the work, and the WebSocket is a second channel from the HTTP response,
 * so an event for a command can reach the slice before the response to it.
 * Two devices are what make that safe rather than lucky:
 *
 *   1. Every write is keyed — by cell id, by name, by session id — so applying
 *      the same event twice leaves the same state.
 *   2. Every write that can be superseded carries the timestamp of the event
 *      that made it (`CellView.lastEventAt`, `ExploreKernelView.lastEventAt`,
 *      `lastMarksAt`), and an event older than the state it would overwrite is
 *      dropped. Two events for one cell therefore converge on the later one
 *      whichever order they arrive in.
 *
 * A third case is not ordering at all: an event can arrive for a session id
 * the slice has never been told the notebook path of, because
 * `session_opened` is published *inside* the open call. Those events are
 * buffered by session id in `pendingExploreEvents` and drained the moment the
 * path is learned, from the `session_opened` event itself or from the POST
 * response, whichever lands first.
 *
 * FR-035: nothing in this file opens a connection to a kernel, and nothing
 * ever should. Every execution goes through the session service.
 */

import type { StateCreator } from "zustand";

import type {
  ExploreBinding,
  ExploreBindingsResponse,
  ExploreCell,
  ExploreCellMarks,
  ExploreCellOutputPayload,
  ExploreCellStatePayload,
  ExploreChangedNamesPayload,
  ExploreCommitRecordedPayload,
  ExploreGraphResponse,
  ExploreKernelListItem,
  ExploreKernelStatePayload,
  ExplorePackagedPayload,
  ExplorePackagingCheckResponse,
  ExploreRequest,
  ExploreSessionEventMessage,
  ExploreSessionOpenedPayload,
} from "../types/api";
import { EXPLORE_EVENT_PREFIX } from "../types/api";
import type {
  ExploreCellMarkKind,
  ExploreCellRunState,
  ExploreKernelDisplayState,
} from "../types/ui";
import type {
  AppStore,
  CellView,
  ExploreKernelView,
  ExploreSessionState,
  ExploreSlice,
  PanelSlot,
  VariableEntry,
} from "./types";

/** The three marks the runtime computes; nothing else is a mark. */
const MARK_KINDS: readonly string[] = ["never_run", "stale", "out_of_order"];

/**
 * How many events are buffered for one not-yet-known session id.
 *
 * A cap rather than an unbounded queue: an event stream for a session whose
 * path never arrives is a bug somewhere else, and letting it grow without
 * limit would turn that bug into a memory leak in this one.
 *
 * TODO(#2253): the overflow is dropped silently rather than reported.
 *   Out of scope per the ADR-054 assembly dispatch (S4-A1 owns T-001 to T-003).
 *   Followup: docs/planning/adr-054-assembly-followups.md, `## S4-A1`.
 */
const PENDING_EVENT_CAP = 200;

function isMarkKind(value: string): value is ExploreCellMarkKind {
  return MARK_KINDS.includes(value);
}

/** Keep only the runtime's own mark vocabulary; an unknown value is not a mark. */
function toMarks(raw: readonly string[] | undefined): ExploreCellMarkKind[] {
  return (raw ?? []).filter(isMarkKind);
}

/**
 * `true` when `candidate` is not older than `held`.
 *
 * A missing held timestamp means nothing has been applied yet, so anything
 * wins; a missing candidate timestamp means the event carried none, and it is
 * treated as current rather than dropped, because dropping a state change on a
 * missing field would be worse than applying it out of order.
 */
function isNotStale(candidate: string | undefined, held: string | null): boolean {
  if (!held) return true;
  if (!candidate) return true;
  return candidate >= held;
}

/**
 * The resting run state a cell reports before any event names it.
 *
 * This reads the runtime's `never_run` mark rather than inferring anything:
 * "the kernel has not run this cell" is the runtime's own statement, and a
 * cell without that mark has run in this kernel, which is `idle`.
 */
function restingRunState(marks: readonly ExploreCellMarkKind[]): ExploreCellRunState {
  return marks.includes("never_run") ? "never-run" : "idle";
}

function cellFromModel(model: ExploreCell, existing?: CellView): CellView {
  const marks = toMarks(model.marks);
  return {
    cellId: model.cell_id ?? "",
    cellType: model.cell_type,
    source: model.source,
    enabled: model.enabled,
    marks,
    // A response is a fresh read of the notebook and the marks; it says
    // nothing about a run in flight, so everything a run wrote is kept.
    outputs: existing?.outputs ?? [],
    outOfOrderReads: existing?.outOfOrderReads ?? [],
    runState: existing?.runState ?? restingRunState(marks),
    executionCount: existing?.executionCount ?? null,
    changedNames: existing?.changedNames ?? [],
    lastEventAt: existing?.lastEventAt ?? null,
  };
}

const EMPTY_KERNEL: ExploreKernelView = {
  state: "not-started",
  pid: null,
  memoryBytes: null,
  needsRestart: false,
  lastEventAt: null,
};

function emptySession(sessionId: string, notebookPath: string): ExploreSessionState {
  return {
    sessionId,
    notebookPath,
    shellState: "opening",
    error: null,
    boundRun: null,
    openedOver: null,
    notebookCommit: null,
    currentCell: null,
    cells: [],
    kernel: { ...EMPTY_KERNEL },
    bindings: [],
    pinnedNames: [],
    panels: [],
    graph: null,
    lastReport: null,
    lastCommit: null,
    lastPackaged: null,
    unobservableNames: [],
    lastAnalysisReason: null,
    lastMarksAt: null,
  };
}

/** Replace one cell in a session by id, leaving every other cell identical. */
function withCell(
  session: ExploreSessionState,
  cellId: string,
  update: (cell: CellView) => CellView,
): ExploreSessionState {
  let touched = false;
  const cells = session.cells.map((cell) => {
    if (cell.cellId !== cellId) return cell;
    touched = true;
    return update(cell);
  });
  if (!touched) return session;
  return { ...session, cells };
}

/**
 * Apply the runtime's whole-session marks map.
 *
 * The map is complete: `_marks_payload` sends every cell that carries a mark,
 * so a cell absent from it carries none. Writing the absences too is what
 * makes a cleared mark actually clear on screen.
 */
function applyMarksMap(
  session: ExploreSessionState,
  marks: Record<string, string[]>,
  at: string | undefined,
): ExploreSessionState {
  if (!isNotStale(at, session.lastMarksAt)) return session;
  return {
    ...session,
    lastMarksAt: at ?? session.lastMarksAt,
    cells: session.cells.map((cell) => {
      const next = toMarks(marks[cell.cellId]);
      const outOfOrderReads = next.includes("out_of_order") ? cell.outOfOrderReads : [];
      return { ...cell, marks: next, outOfOrderReads };
    }),
  };
}

function bindingFromModel(model: ExploreBinding, pinned: boolean): VariableEntry {
  return {
    name: model.name,
    typeName: model.type_name ?? null,
    nativeTypeName: model.native_type_name ?? null,
    summary: model.summary ?? null,
    // Copied, never guessed: FR-018's greying is the runtime's answer.
    live: model.exists_in_kernel,
    pinned,
    openPanelId: null,
    lastBoundBy: model.last_bound_by ?? null,
  };
}

// -- the event appliers -----------------------------------------------------

function applySessionOpened(
  session: ExploreSessionState,
  payload: ExploreSessionOpenedPayload,
): ExploreSessionState {
  return {
    ...session,
    notebookPath: payload.notebook_path,
    openedOver: payload.opened_over ?? session.openedOver,
    // `shellState` stays `opening` until a session *response* lands with the
    // cells: the event says a session exists, not what is in it.
    shellState: session.shellState === "closed" ? "opening" : session.shellState,
    error: null,
  };
}

function applyKernelState(
  session: ExploreSessionState,
  payload: ExploreKernelStatePayload,
  at: string | undefined,
): ExploreSessionState {
  if (!isNotStale(at, session.kernel.lastEventAt)) return session;
  return {
    ...session,
    kernel: {
      // Stored verbatim. `needs-restart` is a value a *renderer* may show in
      // place of this when `needsRestart` is set (FR-016); the slice never
      // substitutes it, because the runtime reports a state and a flag and
      // collapsing them here would lose which one it said.
      state: (payload.state ?? "not-started") as ExploreKernelDisplayState,
      pid: payload.pid ?? null,
      memoryBytes: payload.memory_bytes ?? null,
      needsRestart: Boolean(payload.needs_restart),
      lastEventAt: at ?? session.kernel.lastEventAt,
    },
  };
}

/** The two cell run states the runtime publishes on `cell_state`. */
function runStateFromWire(state: string | null | undefined): ExploreCellRunState | null {
  if (state === "running") return "running";
  if (state === "idle") return "idle";
  if (state === "queued") return "queued";
  return null;
}

function applyCellState(
  session: ExploreSessionState,
  payload: ExploreCellStatePayload,
  at: string | undefined,
): ExploreSessionState {
  let next = session;
  const cellId = payload.cell_id ?? null;
  if (cellId) {
    next = withCell(next, cellId, (cell) => {
      if (!isNotStale(at, cell.lastEventAt)) return cell;
      const runState = runStateFromWire(payload.state);
      // The starting event names the reads that put the cell out of order but
      // not the cells behind them; `applyExploreMarks` fills those in from
      // `MarksResponse`, which is the surface that carries the whole reason.
      const outOfOrderReads = payload.out_of_order
        ? payload.out_of_order.map((name) => ({ name, definer: null, last_binder: null }))
        : cell.outOfOrderReads;
      return {
        ...cell,
        runState: runState ?? cell.runState,
        outOfOrderReads,
        lastEventAt: at ?? cell.lastEventAt,
      };
    });
  }
  if (payload.marks) {
    next = applyMarksMap(next, payload.marks, at);
  }
  return next;
}

function applyCellOutput(
  session: ExploreSessionState,
  payload: ExploreCellOutputPayload,
  at: string | undefined,
): ExploreSessionState {
  return withCell(session, payload.cell_id, (cell) => {
    if (!isNotStale(at, cell.lastEventAt)) return cell;
    return {
      ...cell,
      outputs: payload.outputs ?? [],
      executionCount: payload.execution_count ?? null,
      // The runtime's own status for the run, not a reading of the outputs.
      runState: payload.status === "error" ? "error" : cell.runState,
      lastEventAt: at ?? cell.lastEventAt,
    };
  });
}

function applyChangedNames(
  session: ExploreSessionState,
  payload: ExploreChangedNamesPayload,
): ExploreSessionState {
  const next = withCell(session, payload.cell_id, (cell) => ({
    ...cell,
    changedNames: payload.changed ?? [],
  }));
  return { ...next, unobservableNames: payload.unobservable ?? [] };
}

function applyCommitRecorded(
  session: ExploreSessionState,
  payload: ExploreCommitRecordedPayload,
): ExploreSessionState {
  return {
    ...session,
    lastCommit: payload,
    // Only a branch commit is the notebook's version; the per-run explore
    // commits go to their own ref and are not what packaging reads.
    notebookCommit: payload.ref === "branch" && payload.sha ? payload.sha : session.notebookCommit,
  };
}

function applyPackaged(
  session: ExploreSessionState,
  payload: ExplorePackagedPayload,
): ExploreSessionState {
  return { ...session, lastPackaged: payload };
}

/** Apply one event to one session. Pure, so the ordering rules are testable. */
export function applyEventToSession(
  session: ExploreSessionState,
  message: ExploreSessionEventMessage,
): ExploreSessionState {
  const at = message.timestamp;
  const data = message.data ?? {};
  switch (message.type) {
    case "explore.session_opened":
      return applySessionOpened(session, data as unknown as ExploreSessionOpenedPayload);
    case "explore.session_closed":
      return { ...session, shellState: "closed" };
    case "explore.kernel_state":
      return applyKernelState(session, data as unknown as ExploreKernelStatePayload, at);
    case "explore.cell_state":
      return applyCellState(session, data as unknown as ExploreCellStatePayload, at);
    case "explore.cell_output":
      return applyCellOutput(session, data as unknown as ExploreCellOutputPayload, at);
    case "explore.changed_names":
      return applyChangedNames(session, data as unknown as ExploreChangedNamesPayload);
    case "explore.analysis_updated":
      return { ...session, lastAnalysisReason: (data.reason as string | undefined) ?? null };
    case "explore.commit_recorded":
      return applyCommitRecorded(session, data as unknown as ExploreCommitRecordedPayload);
    case "explore.packaged":
      return applyPackaged(session, data as unknown as ExplorePackagedPayload);
    default:
      return session;
  }
}

/** `true` when this frame is one of the session events this slice consumes. */
export function isExploreSessionEvent(type: string): boolean {
  return type.startsWith(EXPLORE_EVENT_PREFIX);
}

// -- the slice --------------------------------------------------------------

type SliceState = Pick<
  ExploreSlice,
  "sessions" | "sessionPathById" | "exploreKernels" | "pendingExploreEvents"
>;

/**
 * Fold one event into the whole slice state, resolving its session id to a
 * notebook path and buffering it when that path is not known yet.
 */
function reduceEvent(state: SliceState, message: ExploreSessionEventMessage): SliceState {
  const sessionId = message.session_id;
  if (!sessionId) return state;

  // `session_opened` carries the path, so it is the one event that can name a
  // session the slice has never heard of — and the one that drains the buffer.
  let path = state.sessionPathById[sessionId];
  let sessions = state.sessions;
  let sessionPathById = state.sessionPathById;
  let pending = state.pendingExploreEvents;

  if (!path && message.type === "explore.session_opened") {
    const opened = message.data as unknown as ExploreSessionOpenedPayload;
    if (opened?.notebook_path) {
      path = opened.notebook_path;
      sessionPathById = { ...sessionPathById, [sessionId]: path };
      if (!sessions[path]) {
        sessions = { ...sessions, [path]: emptySession(sessionId, path) };
      }
    }
  }

  if (!path) {
    const queue = pending[sessionId] ?? [];
    if (queue.length >= PENDING_EVENT_CAP) return state;
    return { ...state, pendingExploreEvents: { ...pending, [sessionId]: [...queue, message] } };
  }

  const held = sessions[path] ?? emptySession(sessionId, path);
  const updated = applyEventToSession(held, message);
  sessions = { ...sessions, [updated.notebookPath]: updated };
  // `session_opened` may rename the entry when the buffer was keyed on a path
  // learned later; drop the stale key so one session is never two rows.
  if (updated.notebookPath !== path) {
    const { [path]: _dropped, ...rest } = sessions;
    sessions = { ...rest, [updated.notebookPath]: updated };
    sessionPathById = { ...sessionPathById, [sessionId]: updated.notebookPath };
  }

  // Drain anything buffered for this session id now that the path is known.
  const queued = pending[sessionId];
  if (queued && queued.length > 0) {
    const { [sessionId]: _drained, ...restPending } = pending;
    pending = restPending;
    let drainedSession = sessions[updated.notebookPath];
    for (const buffered of queued) {
      drainedSession = applyEventToSession(drainedSession, buffered);
    }
    sessions = { ...sessions, [updated.notebookPath]: drainedSession };
  }

  return {
    sessions,
    sessionPathById,
    exploreKernels: state.exploreKernels,
    pendingExploreEvents: pending,
  };
}

export const createExploreSlice: StateCreator<AppStore, [], [], ExploreSlice> = (set) => ({
  sessions: {},
  sessionPathById: {},
  exploreKernels: [],
  pendingExploreEvents: {},

  applyExploreSession: (session) =>
    set((state) => {
      const path = session.notebook_path;
      const held = state.sessions[path];
      const base = held ?? emptySession(session.session_id, path);
      const byId = new Map(base.cells.map((cell) => [cell.cellId, cell]));
      const cells = session.cells
        .filter((cell) => cell.cell_id)
        .map((cell) => cellFromModel(cell, byId.get(cell.cell_id ?? "")));
      const next: ExploreSessionState = {
        ...base,
        sessionId: session.session_id,
        notebookPath: path,
        shellState: "ready",
        error: null,
        boundRun: session.bound_run,
        openedOver: session.bound_run?.opened_over ?? base.openedOver,
        notebookCommit: session.notebook_commit,
        currentCell: session.current_cell,
        cells,
        kernel: {
          ...base.kernel,
          // The response reports whether a kernel exists and whether it needs a
          // restart; it does not report `busy`, so a live state already written
          // from an event is kept.
          state: session.has_kernel ? base.kernel.state : "not-started",
          needsRestart: session.needs_restart,
        },
        // A response is a snapshot with no timestamp of its own, so the marks
        // ordering guard is reset: any event that arrives after this read wins.
        lastMarksAt: null,
      };
      const sessionPathById = { ...state.sessionPathById, [session.session_id]: path };
      // Drain whatever arrived for this session before its path was known.
      const queued = state.pendingExploreEvents[session.session_id] ?? [];
      let drained = next;
      for (const message of queued) {
        drained = applyEventToSession(drained, message);
      }
      const { [session.session_id]: _consumed, ...pending } = state.pendingExploreEvents;
      return {
        sessions: { ...state.sessions, [path]: drained },
        sessionPathById,
        pendingExploreEvents: pending,
      };
    }),

  applyExploreSessionEvent: (message) =>
    set((state) =>
      reduceEvent(
        {
          sessions: state.sessions,
          sessionPathById: state.sessionPathById,
          exploreKernels: state.exploreKernels,
          pendingExploreEvents: state.pendingExploreEvents,
        },
        message,
      ),
    ),

  applyExploreCells: (sessionId, cells) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const byId = new Map(held.cells.map((cell) => [cell.cellId, cell]));
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            cells: cells
              .filter((cell) => cell.cell_id)
              .map((cell) => cellFromModel(cell, byId.get(cell.cell_id ?? ""))),
          },
        },
      };
    }),

  applyExploreMarks: (sessionId, marks) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const byCell = new Map<string, ExploreCellMarks>(
        marks.marks.map((entry) => [entry.cell_id, entry]),
      );
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            // A marks *response* is the whole truth about marks, so it also
            // resets the ordering guard the events compare against.
            lastMarksAt: null,
            cells: held.cells.map((cell) => {
              const entry = byCell.get(cell.cellId);
              return {
                ...cell,
                marks: toMarks(entry?.marks),
                outOfOrderReads: entry?.out_of_order_reads ?? [],
              };
            }),
          },
        },
      };
    }),

  applyExploreBindings: (sessionId, bindings: ExploreBindingsResponse) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const pinned = new Set(held.pinnedNames);
      const openPanelByName = new Map(held.panels.map((slot) => [slot.boundName, slot.panelId]));
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            bindings: bindings.bindings.map((model) => ({
              ...bindingFromModel(model, pinned.has(model.name)),
              openPanelId: openPanelByName.get(model.name) ?? null,
            })),
          },
        },
      };
    }),

  applyExploreGraph: (sessionId, graph: ExploreGraphResponse) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            graph: {
              cells: graph.cells,
              edges: graph.edges,
              unresolvedReads: graph.unresolved_reads,
              unknownBindingCells: graph.unknown_binding_cells,
              changedSets: graph.changed_sets,
            },
          },
        },
      };
    }),

  applyExplorePackagingReport: (sessionId, report: ExplorePackagingCheckResponse) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      return { sessions: { ...state.sessions, [path]: { ...held, lastReport: report } } };
    }),

  applyExploreRunRequests: (sessionId, requests: ExploreRequest[]) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      // The run response is a response, so FR-034 allows it — and it is the
      // only thing that may put a cell in `queued`, because the runtime
      // publishes no event for a request that is merely waiting.
      const byCell = new Map(requests.map((request) => [request.cell_id, request]));
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            cells: held.cells.map((cell) => {
              const request = byCell.get(cell.cellId);
              if (!request || request.state !== "queued") return cell;
              // Never demote a cell the runtime already said is running.
              if (cell.runState === "running") return cell;
              return { ...cell, runState: "queued" };
            }),
          },
        },
      };
    }),

  applyExploreKernelList: (kernels: ExploreKernelListItem[]) => set({ exploreKernels: kernels }),

  noteExploreSessionOpening: (notebookPath) =>
    set((state) => {
      const held = state.sessions[notebookPath];
      const base = held ?? emptySession("", notebookPath);
      return {
        sessions: {
          ...state.sessions,
          [notebookPath]: { ...base, shellState: "opening", error: null },
        },
      };
    }),

  noteExploreSessionFailed: (notebookPath, error) =>
    set((state) => {
      const held = state.sessions[notebookPath];
      const base = held ?? emptySession("", notebookPath);
      return {
        sessions: {
          ...state.sessions,
          [notebookPath]: { ...base, shellState: "failed", error },
        },
      };
    }),

  noteExplorePanelOpened: (sessionId, slot: PanelSlot) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const panels = held.panels.some((existing) => existing.panelId === slot.panelId)
        ? held.panels.map((existing) => (existing.panelId === slot.panelId ? slot : existing))
        : [...held.panels, slot];
      const pinnedNames = slot.pinned
        ? Array.from(new Set([...held.pinnedNames, slot.boundName]))
        : held.pinnedNames;
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            panels,
            pinnedNames,
            bindings: held.bindings.map((entry) =>
              entry.name === slot.boundName
                ? { ...entry, openPanelId: slot.panelId, pinned: pinnedNames.includes(entry.name) }
                : entry,
            ),
          },
        },
      };
    }),

  noteExplorePanelClosed: (sessionId, panelId) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const closed = held.panels.find((slot) => slot.panelId === panelId);
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            panels: held.panels.filter((slot) => slot.panelId !== panelId),
            bindings: held.bindings.map((entry) =>
              closed && entry.name === closed.boundName ? { ...entry, openPanelId: null } : entry,
            ),
          },
        },
      };
    }),

  setExplorePanelPinned: (sessionId, panelId, pinned) =>
    set((state) => {
      const path = state.sessionPathById[sessionId];
      const held = path ? state.sessions[path] : undefined;
      if (!path || !held) return {};
      const slot = held.panels.find((candidate) => candidate.panelId === panelId);
      if (!slot) return {};
      const pinnedNames = pinned
        ? Array.from(new Set([...held.pinnedNames, slot.boundName]))
        : held.pinnedNames.filter((name) => name !== slot.boundName);
      return {
        sessions: {
          ...state.sessions,
          [path]: {
            ...held,
            pinnedNames,
            panels: held.panels.map((candidate) =>
              candidate.panelId === panelId ? { ...candidate, pinned } : candidate,
            ),
            bindings: held.bindings.map((entry) =>
              entry.name === slot.boundName ? { ...entry, pinned } : entry,
            ),
          },
        },
      };
    }),

  forgetExploreSession: (notebookPath) =>
    set((state) => {
      const held = state.sessions[notebookPath];
      if (!held) return {};
      const { [notebookPath]: _dropped, ...sessions } = state.sessions;
      const sessionPathById = Object.fromEntries(
        Object.entries(state.sessionPathById).filter(([, path]) => path !== notebookPath),
      );
      return { sessions, sessionPathById };
    }),
});

/** Read one session out of the store by its notebook path. */
export function selectExploreSession(
  state: AppStore,
  notebookPath: string,
): ExploreSessionState | undefined {
  return state.sessions[notebookPath];
}

/** The store getter the shell uses when it holds a session id rather than a path. */
export function selectExploreSessionById(
  state: AppStore,
  sessionId: string,
): ExploreSessionState | undefined {
  const path = state.sessionPathById[sessionId];
  return path ? state.sessions[path] : undefined;
}

export { emptySession as emptyExploreSession, restingRunState as exploreRestingRunState };
