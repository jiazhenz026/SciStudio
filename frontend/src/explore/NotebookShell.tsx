/**
 * ADR-054 spec 4 (T-004, T-007) — the notebook shell (FR-008 to FR-011,
 * FR-017).
 *
 * SciStudio's own cell list. No notebook library is introduced: JupyterLab's
 * components carry a widget system foreign to this application and a kernel
 * client that would bypass the session service, and every execution here has to
 * go through that service (FR-035).
 *
 * **Virtualisation is the first thing this file does, not a later
 * optimisation.** Only the cells the viewport reports as on screen mount a
 * Monaco editor (FR-008); every other cell renders as highlighted static text.
 * Spec §4.5 names editor cost as the first risk of the whole spec, and a
 * two-hundred-cell notebook with two hundred editor instances is the failure it
 * names. Where the browser has no `IntersectionObserver`, the shell falls back
 * to a **bounded prefix window** rather than to "mount everything", so the
 * guarantee holds in every environment.
 *
 * **A draft lives here, not in a Monaco model.** `drafts` is keyed by cell id,
 * so an editor unmounted by a scroll and remounted by a scroll back finds its
 * text waiting; the static text a swapped-out cell renders is the draft, not
 * the runtime's source. Drafts are written to the session API on a debounce and
 * on run (FR-017), and never anywhere else.
 *
 * **A reload keeps the person's typing.** When the notebook changes under an
 * unsaved draft, `reconcileDrafts` keeps the draft, records the source it now
 * disagrees with, and marks the cell conflicting until the person keeps or
 * discards it (FR-017, spec §2 "The notebook is edited outside SciStudio").
 * Nothing typed is dropped and nothing is auto-resolved.
 *
 * **Nothing here computes a mark, a kernel state, or a binding** (FR-034). The
 * marks come from the runtime through `CellMarks`; a command's effect appears
 * when the response or the event that carries it reaches the slice.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { exploreApi } from "../lib/api/explore";
import { logger } from "../lib/logger";
import { useAppStore } from "../store";
import type { CellView, ExploreSessionState, ExploreTab } from "../store/types";

import { CellEditor, StaticCellSource } from "./CellEditor";
import { CellMarks } from "./CellMarks";
import { OutputRenderer } from "./OutputRenderer";

/** FR-017 — how long the shell waits after the last keystroke before saving. */
export const CELL_SAVE_DEBOUNCE_MS = 600;
/** Cells this far outside the viewport still carry an editor, so a slow scroll
 *  does not flicker between static and live text. */
const EDITOR_WINDOW_OVERSCAN_PX = 240;
/** The bound when the browser cannot report visibility at all (FR-008). */
export const FALLBACK_EDITOR_WINDOW = 10;

const EMPTY_CELLS: CellView[] = [];

// -- drafts and the reload reconciliation (FR-017) --------------------------

/** One cell's unsaved text, and what the runtime said when it was started. */
export interface CellDraft {
  /** What the person has typed and the session API has not been told yet. */
  text: string;
  /** The runtime's source this draft was started from. */
  base: string;
  /** FR-017 — the notebook was reloaded under this draft. */
  conflicting: boolean;
}

export type CellDrafts = Record<string, CellDraft>;

/**
 * Reconcile the drafts with the cells the runtime now reports, by cell id.
 *
 * Three cases, and the middle one is the requirement:
 *
 *   - the runtime's source is now the draft's text — the write landed, so the
 *     draft is dropped and the cell is simply saved;
 *   - the runtime's source changed and is not the draft's text — **the draft is
 *     kept** and the cell is marked conflicting, with `base` moved to what the
 *     runtime now says, so the conflict is reported once rather than on every
 *     later render;
 *   - a draft whose cell id is gone — kept, untouched. nbformat ids are stable,
 *     so a cell that comes back is the same cell and its draft is still the
 *     person's; a draft is never dropped merely because a cell left the list.
 *
 * Pure and exported so the reconciliation can be tested without a component.
 */
export function reconcileDrafts(drafts: CellDrafts, cells: readonly CellView[]): CellDrafts {
  const byId = new Map(cells.map((cell) => [cell.cellId, cell]));
  const next: CellDrafts = {};
  let changed = false;
  for (const [cellId, draft] of Object.entries(drafts)) {
    const cell = byId.get(cellId);
    if (!cell) {
      next[cellId] = draft;
      continue;
    }
    if (cell.source === draft.text) {
      changed = true;
      continue;
    }
    if (cell.source === draft.base) {
      next[cellId] = draft;
      continue;
    }
    next[cellId] = { text: draft.text, base: cell.source, conflicting: true };
    changed = true;
  }
  return changed ? next : drafts;
}

// -- virtualisation (FR-008) ------------------------------------------------

interface VisibleCells {
  visible: Set<string>;
  rowRef: (cellId: string) => (element: HTMLElement | null) => void;
}

/**
 * Which cells are on screen.
 *
 * `IntersectionObserver` rather than a measured scroll window because cell
 * heights are not knowable in advance: a cell's height is its source plus its
 * outputs, and an image output can be any size at all. The observer answers the
 * only question the shell actually has — "is this row in view" — without the
 * shell having to model the layout.
 */
function useVisibleCells(cellIds: readonly string[]): VisibleCells {
  const [visible, setVisible] = useState<Set<string>>(() => new Set());
  const elements = useRef(new Map<string, HTMLElement>());
  const observer = useRef<IntersectionObserver | null>(null);
  const callbacks = useRef(new Map<string, (element: HTMLElement | null) => void>());

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      // No visibility to observe: a bounded prefix rather than the whole
      // notebook, so the editor-count guarantee holds even here.
      setVisible(new Set(cellIds.slice(0, FALLBACK_EDITOR_WINDOW)));
      return;
    }
    const live = new IntersectionObserver(
      (entries) => {
        setVisible((held) => {
          const next = new Set(held);
          let changed = false;
          for (const entry of entries) {
            const cellId = (entry.target as HTMLElement).dataset.cellId;
            if (!cellId) continue;
            if (entry.isIntersecting) {
              if (!next.has(cellId)) {
                next.add(cellId);
                changed = true;
              }
            } else if (next.delete(cellId)) {
              changed = true;
            }
          }
          return changed ? next : held;
        });
      },
      { rootMargin: `${EDITOR_WINDOW_OVERSCAN_PX}px 0px` },
    );
    observer.current = live;
    for (const element of elements.current.values()) live.observe(element);
    return () => {
      live.disconnect();
      observer.current = null;
    };
  }, [cellIds]);

  const rowRef = useCallback((cellId: string) => {
    let held = callbacks.current.get(cellId);
    if (!held) {
      // One stable callback per cell id: a fresh arrow function per render
      // would detach and reattach every row on every render, and the observer
      // would spend its life re-observing rows that never moved.
      held = (element: HTMLElement | null) => {
        const previous = elements.current.get(cellId);
        if (previous && observer.current) observer.current.unobserve(previous);
        if (element) {
          elements.current.set(cellId, element);
          observer.current?.observe(element);
        } else {
          elements.current.delete(cellId);
        }
      };
      callbacks.current.set(cellId, held);
    }
    return held;
  }, []);

  return { visible, rowRef };
}

// -- one cell ---------------------------------------------------------------

const RUN_STATE_CLASS: Record<string, string> = {
  "never-run": "text-stone-400",
  queued: "text-blue-700",
  running: "text-blue-700",
  idle: "text-stone-500",
  error: "text-red-700",
};

/**
 * The session API has no route for these two, so the controls are shown and
 * refused rather than hidden — hiding them would make the shell look complete.
 *
 * TODO(#2253): send delete and move once the session API carries them.
 *   Out of scope per the ADR-054 assembly dispatch: the routes are
 *   `src/scistudio/**`, which no agent in this dispatch may change.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `### S4-A2`,
 *   entry F-A2-001.
 */
const NO_ROUTE_TITLE =
  "The Explore session API carries no route for this yet — see the ADR-054 follow-up register, S4-A2 F-A2-001.";

interface CellRowProps {
  cell: CellView;
  draft: CellDraft | undefined;
  /** FR-008 — whether this cell is one of the ones carrying an editor. */
  editorMounted: boolean;
  markdownEditing: boolean;
  /** `true` when there is no session to send a command to. */
  disabled: boolean;
  rowRef: (element: HTMLElement | null) => void;
  onChange: (cell: CellView, text: string) => void;
  onRun: (cellId: string) => void;
  onRunWithUpstream: (cellId: string) => void;
  onInsertAfter: (cellId: string) => void;
  onToggleEnabled: (cell: CellView) => void;
  onEditMarkdown: (cellId: string, editing: boolean) => void;
  onKeepDraft: (cellId: string) => void;
  onDiscardDraft: (cellId: string) => void;
}

function CellRow({
  cell,
  draft,
  editorMounted,
  markdownEditing,
  disabled,
  rowRef,
  onChange,
  onRun,
  onRunWithUpstream,
  onInsertAfter,
  onToggleEnabled,
  onEditMarkdown,
  onKeepDraft,
  onDiscardDraft,
}: CellRowProps) {
  const source = draft?.text ?? cell.source;
  const isMarkdown = cell.cellType === "markdown";
  const language = isMarkdown ? "markdown" : "python";
  // The editor set is exactly the visible set — a markdown cell being edited
  // that scrolls away renders its draft as markdown and resumes editing when
  // it comes back, rather than becoming an exception to FR-008's bound.
  const showEditor = isMarkdown ? markdownEditing && editorMounted : editorMounted;

  return (
    <li
      className={`rounded border px-2 py-2 ${cell.enabled ? "border-stone-200 bg-white/70" : "border-stone-200 bg-stone-100/70 opacity-70"}`}
      data-cell-id={cell.cellId}
      data-cell-kind={cell.cellType}
      data-editor-mounted={showEditor ? "true" : "false"}
      data-run-state={cell.runState}
      data-testid={`explore-cell-${cell.cellId}`}
      ref={rowRef}
    >
      <div className="flex items-center gap-2 pb-1 text-[11px] text-stone-500">
        <span
          className="font-mono text-stone-400"
          data-testid={`explore-cell-count-${cell.cellId}`}
        >
          [{cell.executionCount ?? " "}]
        </span>
        <span className={RUN_STATE_CLASS[cell.runState] ?? "text-stone-500"}>{cell.runState}</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            className="toolbar-button"
            data-testid={`explore-cell-run-${cell.cellId}`}
            disabled={disabled}
            onClick={() => onRun(cell.cellId)}
            type="button"
          >
            Run
          </button>
          {isMarkdown ? (
            <button
              className="toolbar-button"
              data-testid={`explore-cell-edit-${cell.cellId}`}
              onClick={() => onEditMarkdown(cell.cellId, !markdownEditing)}
              type="button"
            >
              {markdownEditing ? "Done" : "Edit"}
            </button>
          ) : null}
          <label className="flex items-center gap-1" htmlFor={`enabled-${cell.cellId}`}>
            <input
              checked={cell.enabled}
              data-testid={`explore-cell-enabled-${cell.cellId}`}
              disabled={disabled}
              id={`enabled-${cell.cellId}`}
              onChange={() => onToggleEnabled(cell)}
              type="checkbox"
            />
            enabled
          </label>
          <button
            className="toolbar-button"
            data-testid={`explore-cell-insert-${cell.cellId}`}
            disabled={disabled}
            onClick={() => onInsertAfter(cell.cellId)}
            type="button"
          >
            Add below
          </button>
          <button
            className="toolbar-button"
            data-testid={`explore-cell-move-up-${cell.cellId}`}
            disabled
            title={NO_ROUTE_TITLE}
            type="button"
          >
            Move up
          </button>
          <button
            className="toolbar-button"
            data-testid={`explore-cell-move-down-${cell.cellId}`}
            disabled
            title={NO_ROUTE_TITLE}
            type="button"
          >
            Move down
          </button>
          <button
            className="toolbar-button"
            data-testid={`explore-cell-delete-${cell.cellId}`}
            disabled
            title={NO_ROUTE_TITLE}
            type="button"
          >
            Delete
          </button>
        </div>
      </div>

      <CellMarks cell={cell} disabled={disabled} onRunWithUpstream={onRunWithUpstream} />

      {draft?.conflicting ? (
        <div
          className="mb-1 flex flex-wrap items-center gap-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] text-amber-900"
          data-testid={`explore-cell-conflict-${cell.cellId}`}
        >
          <span>
            The notebook was reloaded while this cell had unsaved edits. Your text is kept.
          </span>
          <button
            className="rounded border border-amber-400 px-2 py-0.5"
            data-testid={`explore-cell-keep-draft-${cell.cellId}`}
            disabled={disabled}
            onClick={() => onKeepDraft(cell.cellId)}
            type="button"
          >
            Keep mine
          </button>
          <button
            className="rounded border border-amber-400 px-2 py-0.5"
            data-testid={`explore-cell-discard-draft-${cell.cellId}`}
            onClick={() => onDiscardDraft(cell.cellId)}
            type="button"
          >
            Discard mine
          </button>
        </div>
      ) : null}

      {showEditor ? (
        <CellEditor
          cellId={cell.cellId}
          language={language}
          onChange={(text) => onChange(cell, text)}
          readOnly={!cell.enabled}
          value={source}
        />
      ) : isMarkdown ? (
        <div
          className="prose-sm max-w-none rounded border border-transparent px-1 text-[13px] text-stone-700"
          data-testid={`explore-cell-markdown-${cell.cellId}`}
          onDoubleClick={() => onEditMarkdown(cell.cellId, true)}
        >
          <Markdown remarkPlugins={[remarkGfm]}>{source}</Markdown>
        </div>
      ) : (
        <StaticCellSource cellId={cell.cellId} language={language} source={source} />
      )}

      <OutputRenderer cellId={cell.cellId} outputs={cell.outputs} />
    </li>
  );
}

// -- the shell --------------------------------------------------------------

export interface NotebookShellProps {
  tab: ExploreTab;
  /** `undefined` until the open or restore lands. */
  session: ExploreSessionState | undefined;
}

export function NotebookShell({ tab, session }: NotebookShellProps) {
  const applyExploreCells = useAppStore((state) => state.applyExploreCells);
  const applyExploreRunRequests = useAppStore((state) => state.applyExploreRunRequests);

  const sessionId = session?.sessionId ?? "";
  const cells = session?.cells ?? EMPTY_CELLS;
  const cellIds = useMemo(() => cells.map((cell) => cell.cellId), [cells]);
  const reloadReason = session?.lastAnalysisReason ?? null;

  const [drafts, setDrafts] = useState<CellDrafts>({});
  const [markdownEditing, setMarkdownEditing] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const { visible, rowRef } = useVisibleCells(cellIds);

  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const refuse = useCallback((what: string, cause: unknown) => {
    const message = cause instanceof Error ? cause.message : String(cause);
    logger.error(`explore: ${what}`, { error: message });
    setError(`${what}: ${message}`);
  }, []);

  // -- writing (FR-017) -----------------------------------------------------

  const writeCell = useCallback(
    async (cellId: string, text: string) => {
      const id = sessionIdRef.current;
      if (!id) return;
      setError(null);
      try {
        const response = await exploreApi.writeExploreCell(id, cellId, text);
        applyExploreCells(id, response.cells);
        setDrafts((held) => {
          const draft = held[cellId];
          // Typed on while the write was in flight: that text is still unsaved.
          if (!draft || draft.text !== text) return held;
          const { [cellId]: _saved, ...rest } = held;
          return rest;
        });
      } catch (cause) {
        refuse("Saving the cell failed", cause);
      }
    },
    [applyExploreCells, refuse],
  );

  const cancelTimer = useCallback((cellId: string) => {
    const timer = timers.current.get(cellId);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(cellId);
    }
  }, []);

  const scheduleSave = useCallback(
    (cellId: string, text: string) => {
      cancelTimer(cellId);
      timers.current.set(
        cellId,
        setTimeout(() => {
          timers.current.delete(cellId);
          void writeCell(cellId, text);
        }, CELL_SAVE_DEBOUNCE_MS),
      );
    },
    [cancelTimer, writeCell],
  );

  /**
   * Save a cell's draft now.
   *
   * A conflicting draft is not saved by the debounce — writing it would
   * overwrite the edit that arrived from outside without anybody deciding to.
   * `force` is the deciding: it is what "Run" and "Keep mine" pass.
   */
  const flushSave = useCallback(
    async (cellId: string, force = false) => {
      cancelTimer(cellId);
      const draft = draftsRef.current[cellId];
      if (!draft) return;
      if (draft.conflicting && !force) return;
      await writeCell(cellId, draft.text);
    },
    [cancelTimer, writeCell],
  );

  const onChange = useCallback(
    (cell: CellView, text: string) => {
      setDrafts((held) => {
        const draft = held[cell.cellId];
        if (text === cell.source && !draft?.conflicting) {
          if (!draft) return held;
          const { [cell.cellId]: _reverted, ...rest } = held;
          return rest;
        }
        return {
          ...held,
          [cell.cellId]: {
            text,
            base: draft?.base ?? cell.source,
            conflicting: draft?.conflicting ?? false,
          },
        };
      });
      // A conflicting draft is never saved by typing: the debounce would
      // overwrite the edit that arrived from outside without anybody deciding
      // to. "Keep mine" and "Run" are the two decisions that save it.
      if (draftsRef.current[cell.cellId]?.conflicting) return;
      scheduleSave(cell.cellId, text);
    },
    [scheduleSave],
  );

  // -- the commands (FR-010, FR-013) ---------------------------------------

  const onRun = useCallback(
    async (cellId: string) => {
      const id = sessionIdRef.current;
      if (!id) return;
      // FR-017 — an edit goes to the API on run, whatever the debounce was
      // about to do. Running the runtime's older source would run something
      // the person is not looking at.
      await flushSave(cellId, true);
      setError(null);
      try {
        const response = await exploreApi.runExploreCell(id, cellId);
        applyExploreRunRequests(id, response.requests);
      } catch (cause) {
        refuse("Running the cell failed", cause);
      }
    },
    [applyExploreRunRequests, flushSave, refuse],
  );

  const onRunWithUpstream = useCallback(
    async (cellId: string) => {
      const id = sessionIdRef.current;
      if (!id) return;
      await flushSave(cellId, true);
      setError(null);
      try {
        const response = await exploreApi.runExploreWithUpstream(id, cellId);
        applyExploreRunRequests(id, response.requests);
      } catch (cause) {
        refuse("Running the cell with its upstream failed", cause);
      }
    },
    [applyExploreRunRequests, flushSave, refuse],
  );

  const onInsertAfter = useCallback(
    async (after: string | null) => {
      const id = sessionIdRef.current;
      if (!id) return;
      setError(null);
      try {
        const response = await exploreApi.insertExploreCell(id, "", after);
        applyExploreCells(id, response.cells);
      } catch (cause) {
        refuse("Adding a cell failed", cause);
      }
    },
    [applyExploreCells, refuse],
  );

  const onToggleEnabled = useCallback(
    async (cell: CellView) => {
      const id = sessionIdRef.current;
      if (!id) return;
      setError(null);
      try {
        const response = await exploreApi.setExploreCellEnabled(id, cell.cellId, !cell.enabled);
        applyExploreCells(id, response.cells);
      } catch (cause) {
        refuse("Changing the cell's enabled state failed", cause);
      }
    },
    [applyExploreCells, refuse],
  );

  const onKeepDraft = useCallback((cellId: string) => void flushSave(cellId, true), [flushSave]);

  const onDiscardDraft = useCallback(
    (cellId: string) => {
      cancelTimer(cellId);
      setDrafts((held) => {
        const { [cellId]: _discarded, ...rest } = held;
        return rest;
      });
    },
    [cancelTimer],
  );

  const onEditMarkdown = useCallback((cellId: string, editing: boolean) => {
    setMarkdownEditing((held) => ({ ...held, [cellId]: editing }));
  }, []);

  // -- the reconciliation (FR-017) -----------------------------------------

  // Every path that rewrites the cells passes through here: a write response,
  // an insert response, and the re-read after an external edit.
  useEffect(() => {
    setDrafts((held) => reconcileDrafts(held, cells));
  }, [cells]);

  /**
   * Re-read the cells when the runtime says the file changed underneath.
   *
   * `analysis_updated` with `reason: "external_edit"` is what
   * `ExploreSession.reload_if_changed` publishes; the event carries no cells,
   * so the shell asks for them. Every other reason already arrived with its
   * cells in a response.
   */
  useEffect(() => {
    if (reloadReason !== "external_edit" || !sessionId) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await exploreApi.readExploreCells(sessionId);
        if (!cancelled) applyExploreCells(sessionId, response.cells);
      } catch (cause) {
        if (!cancelled) refuse("Re-reading the reloaded notebook failed", cause);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyExploreCells, refuse, reloadReason, sessionId]);

  /**
   * On unmount, send what the debounce had not sent yet.
   *
   * A tab switch unmounts the shell, and a draft that is only in this
   * component's state would go with it. A conflicting draft is deliberately not
   * flushed: it is unsaved because nobody has decided between it and the file.
   *
   * TODO(#2253): a conflicting draft is still lost on a tab switch, because
   *   drafts live in this component rather than in the session slice.
   *   Out of scope per the ADR-054 assembly dispatch: `store/exploreSlice.ts`
   *   and `store/types.ts` are S4-A1's write set.
   *   Followup: docs/planning/adr-054-assembly-followups.md, `### S4-A2`,
   *   entry F-A2-002.
   */
  useEffect(() => {
    const held = timers.current;
    return () => {
      for (const timer of held.values()) clearTimeout(timer);
      held.clear();
      const id = sessionIdRef.current;
      if (!id) return;
      for (const [cellId, draft] of Object.entries(draftsRef.current)) {
        if (draft.conflicting) continue;
        void exploreApi.writeExploreCell(id, cellId, draft.text).catch((cause: unknown) => {
          logger.error("explore: flushing a draft on unmount failed", {
            error: cause instanceof Error ? cause.message : String(cause),
          });
        });
      }
    };
  }, []);

  // -- rendering ------------------------------------------------------------

  const disabled = sessionId === "";
  const lastCellId = cells.length > 0 ? cells[cells.length - 1].cellId : null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" data-testid="explore-notebook-shell">
      <div className="flex items-center gap-2 text-[11px] text-stone-500">
        <span data-testid="explore-notebook-path">{tab.notebookPath}</span>
        <span className="ml-auto" data-testid="explore-notebook-cell-count">
          {cells.length} cells
        </span>
      </div>

      {error ? (
        <p
          className="rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-800"
          data-testid="explore-notebook-error"
        >
          {error}
        </p>
      ) : null}

      {session === undefined ? (
        <p className="text-xs text-stone-400" data-testid="explore-notebook-opening">
          Opening the session…
        </p>
      ) : null}

      <ul className="flex flex-col gap-2" data-testid="explore-notebook-cells">
        {cells.map((cell) => (
          <CellRow
            cell={cell}
            disabled={disabled}
            draft={drafts[cell.cellId]}
            editorMounted={visible.has(cell.cellId)}
            key={cell.cellId}
            markdownEditing={markdownEditing[cell.cellId] ?? false}
            onChange={onChange}
            onDiscardDraft={onDiscardDraft}
            onEditMarkdown={onEditMarkdown}
            onInsertAfter={(cellId) => void onInsertAfter(cellId)}
            onKeepDraft={onKeepDraft}
            onRun={(cellId) => void onRun(cellId)}
            onRunWithUpstream={(cellId) => void onRunWithUpstream(cellId)}
            onToggleEnabled={(target) => void onToggleEnabled(target)}
            rowRef={rowRef(cell.cellId)}
          />
        ))}
      </ul>

      <button
        className="toolbar-button self-start"
        data-testid="explore-notebook-add-cell"
        disabled={disabled}
        onClick={() => void onInsertAfter(lastCellId)}
        type="button"
      >
        Add cell
      </button>
    </div>
  );
}

export default NotebookShell;
