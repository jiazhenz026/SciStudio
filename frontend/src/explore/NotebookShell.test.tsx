/**
 * ADR-054 spec 4 (T-004, T-007) — the notebook shell (FR-008 to FR-010,
 * FR-017; SC-002).
 *
 * The assertion this file exists for is the editor count. Spec §4.5 names
 * editor cost as the first risk of the whole spec, and "only the visible cells
 * carry an editor" is the kind of claim that is true on the day it is written
 * and quietly false a month later, so it is measured here against notebooks of
 * three sizes rather than described.
 *
 * The second one is the draft. A draft that lived in a Monaco model would be
 * destroyed by the scroll that unmounts the editor, and the person would lose
 * what they typed by scrolling — which is why the shell holds drafts by cell id
 * and why the swap is driven here from a controllable `IntersectionObserver`
 * rather than left to a real viewport that jsdom does not have.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import type { ExploreCellsResponse, ExploreSessionResponse } from "../types/api";

import { FALLBACK_EDITOR_WINDOW, NotebookShell, reconcileDrafts } from "./NotebookShell";
import type { CellDrafts } from "./NotebookShell";
import type { ExploreTab as ExploreTabState } from "../store/types";

// The editor is mocked as a textarea so a keystroke is a real DOM event; what
// is under test is the shell's bookkeeping, not Monaco's.
vi.mock("@monaco-editor/react", () => ({
  default: (props: {
    path?: string;
    value?: string;
    language?: string;
    options?: { readOnly?: boolean };
    onChange?: (value: string | undefined) => void;
  }) => (
    <textarea
      data-language={props.language}
      data-testid={`monaco-${props.path}`}
      onChange={(event) => props.onChange?.(event.target.value)}
      readOnly={props.options?.readOnly}
      value={props.value ?? ""}
    />
  ),
}));

const writeExploreCell = vi.fn();
const insertExploreCell = vi.fn();
const setExploreCellEnabled = vi.fn();
const runExploreCell = vi.fn();
const runExploreWithUpstream = vi.fn();
const readExploreCells = vi.fn();

vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    writeExploreCell: (...args: unknown[]) => writeExploreCell(...args),
    insertExploreCell: (...args: unknown[]) => insertExploreCell(...args),
    setExploreCellEnabled: (...args: unknown[]) => setExploreCellEnabled(...args),
    runExploreCell: (...args: unknown[]) => runExploreCell(...args),
    runExploreWithUpstream: (...args: unknown[]) => runExploreWithUpstream(...args),
    readExploreCells: (...args: unknown[]) => readExploreCells(...args),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-shell";

function tab(): ExploreTabState {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: SESSION_ID,
    displayName: "analysis.ipynb",
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
  };
}

function sessionOf(
  count: number,
  overrides: Partial<ExploreSessionResponse> = {},
): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: true,
    needs_restart: false,
    current_cell: "c0",
    notebook_commit: null,
    bound_run: null,
    cells: Array.from({ length: count }, (_, index) => ({
      cell_id: `c${index}`,
      cell_type: "code",
      source: `value_${index} = ${index}`,
      enabled: true,
      marks: [],
    })),
    ...overrides,
  };
}

function cellsResponse(cells: ExploreSessionResponse["cells"]): ExploreCellsResponse {
  return { session_id: SESSION_ID, cells };
}

type WireCell = ExploreSessionResponse["cells"][number];

/** The notebook as the slice currently holds it, in the route's wire shape. */
function heldCells(mutate: (cell: WireCell) => WireCell = (cell) => cell): WireCell[] {
  const held = useAppStore.getState().sessions[PATH];
  return (held?.cells ?? []).map((cell) =>
    mutate({
      cell_id: cell.cellId,
      cell_type: cell.cellType,
      source: cell.source,
      enabled: cell.enabled,
      marks: [...cell.marks],
    }),
  );
}

/** Subscribes like `ExploreTab` does, so a store write re-renders the shell. */
function Shell() {
  const session = useAppStore((state) => state.sessions[PATH]);
  return <NotebookShell session={session} tab={tab()} />;
}

// -- a controllable IntersectionObserver ------------------------------------

interface FakeObserver {
  callback: IntersectionObserverCallback;
  targets: Set<Element>;
}

const observers: FakeObserver[] = [];

class ControllableIntersectionObserver {
  private entry: FakeObserver;
  constructor(callback: IntersectionObserverCallback) {
    this.entry = { callback, targets: new Set() };
    observers.push(this.entry);
  }
  observe(target: Element) {
    this.entry.targets.add(target);
  }
  unobserve(target: Element) {
    this.entry.targets.delete(target);
  }
  disconnect() {
    this.entry.targets.clear();
    const at = observers.indexOf(this.entry);
    if (at >= 0) observers.splice(at, 1);
  }
  takeRecords() {
    return [];
  }
}

function installObserver() {
  vi.stubGlobal("IntersectionObserver", ControllableIntersectionObserver);
}

/** Report exactly these cells as on screen and every other cell as off it. */
function showOnly(cellIds: string[]) {
  const wanted = new Set(cellIds);
  act(() => {
    for (const observer of [...observers]) {
      const entries = [...observer.targets].map((target) => ({
        target,
        isIntersecting: wanted.has((target as HTMLElement).dataset.cellId ?? ""),
      }));
      observer.callback(
        entries as unknown as IntersectionObserverEntry[],
        {} as IntersectionObserver,
      );
    }
  });
}

function mountedEditorCount(): number {
  return document.querySelectorAll('[data-editor-mounted="true"]').length;
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  observers.length = 0;
  for (const spy of [
    writeExploreCell,
    insertExploreCell,
    setExploreCellEnabled,
    runExploreCell,
    runExploreWithUpstream,
    readExploreCells,
  ]) {
    spy.mockReset();
  }
  // The default answers are the route's real answer: the *whole* notebook back,
  // with the change applied. A stub that answered with a one-cell notebook
  // would silently truncate the notebook under a test that only meant to type.
  writeExploreCell.mockImplementation(async (_sessionId: string, cellId: string, source: string) =>
    cellsResponse(heldCells((cell) => (cell.cell_id === cellId ? { ...cell, source } : cell))),
  );
  insertExploreCell.mockImplementation(async () => cellsResponse(heldCells()));
  setExploreCellEnabled.mockImplementation(
    async (_sessionId: string, cellId: string, enabled: boolean) =>
      cellsResponse(heldCells((cell) => (cell.cell_id === cellId ? { ...cell, enabled } : cell))),
  );
  runExploreCell.mockResolvedValue({ session_id: SESSION_ID, requests: [] });
  runExploreWithUpstream.mockResolvedValue({ session_id: SESSION_ID, requests: [] });
  readExploreCells.mockResolvedValue(cellsResponse(sessionOf(1).cells));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("only the visible cells carry an editor (FR-008, SC-002)", () => {
  it.each([12, 60, 200])(
    "bounds the editor count in a notebook of %i cells when nothing reports visibility",
    (count) => {
      // jsdom has no IntersectionObserver, which is the environment the
      // fallback exists for: a bounded prefix, never the whole notebook.
      expect(typeof IntersectionObserver).toBe("undefined");
      act(() => useAppStore.getState().applyExploreSession(sessionOf(count)));
      render(<Shell />);
      expect(mountedEditorCount()).toBe(FALLBACK_EDITOR_WINDOW);
      expect(document.querySelectorAll('[data-editor-mounted="false"]')).toHaveLength(
        count - FALLBACK_EDITOR_WINDOW,
      );
      // Every cell without an editor still shows its source, highlighted.
      expect(screen.getByTestId(`explore-cell-static-c${count - 1}`)).toBeTruthy();
    },
  );

  it("mounts editors for exactly the cells the viewport reports", () => {
    installObserver();
    act(() => useAppStore.getState().applyExploreSession(sessionOf(30)));
    render(<Shell />);
    // Nothing has been reported visible yet.
    expect(mountedEditorCount()).toBe(0);

    showOnly(["c5", "c6", "c7"]);
    expect(mountedEditorCount()).toBe(3);
    for (const cellId of ["c5", "c6", "c7"]) {
      expect(screen.getByTestId(`explore-cell-${cellId}`).dataset.editorMounted).toBe("true");
    }
    expect(screen.getByTestId("explore-cell-c8").dataset.editorMounted).toBe("false");

    showOnly(["c20"]);
    expect(mountedEditorCount()).toBe(1);
    expect(screen.getByTestId("explore-cell-c20").dataset.editorMounted).toBe("true");
  });

  it("keeps an unsaved draft when the editor is swapped out and back", async () => {
    installObserver();
    act(() => useAppStore.getState().applyExploreSession(sessionOf(30)));
    render(<Shell />);
    showOnly(["c6"]);

    const editor = await screen.findByTestId("monaco-explore-cell/c6");
    fireEvent.change(editor, { target: { value: "value_6 = 'edited but not saved'" } });

    // Scrolled away: the editor is gone and the draft is what the static text
    // shows — not the runtime's source, which would look like a lost edit.
    showOnly(["c20"]);
    expect(screen.getByTestId("explore-cell-c6").dataset.editorMounted).toBe("false");
    expect(screen.getByTestId("explore-cell-static-c6").textContent).toContain(
      "edited but not saved",
    );

    // Scrolled back: the same text is in the editor again.
    showOnly(["c6"]);
    const returned = await screen.findByTestId("monaco-explore-cell/c6");
    expect((returned as HTMLTextAreaElement).value).toBe("value_6 = 'edited but not saved'");
  });
});

describe("edits reach the session API (FR-017)", () => {
  it("writes one debounced save for a run of keystrokes", async () => {
    vi.useFakeTimers();
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    render(<Shell />);
    const editor = await vi.waitFor(() => screen.getByTestId("monaco-explore-cell/c0"));

    for (const text of ["v", "va", "val"]) {
      fireEvent.change(editor, { target: { value: text } });
    }
    await act(async () => {
      vi.advanceTimersByTime(599);
    });
    expect(writeExploreCell).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(2);
    });
    expect(writeExploreCell).toHaveBeenCalledTimes(1);
    expect(writeExploreCell).toHaveBeenCalledWith(SESSION_ID, "c0", "val");
  });

  it("saves the draft before it runs the cell, and reflects only the response", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    runExploreCell.mockResolvedValue({
      session_id: SESSION_ID,
      requests: [{ request_id: "r1", cell_id: "c0", kind: "cell", state: "queued" }],
    });
    render(<Shell />);
    const editor = await screen.findByTestId("monaco-explore-cell/c0");
    fireEvent.change(editor, { target: { value: "value_0 = 99" } });

    fireEvent.click(screen.getByTestId("explore-cell-run-c0"));
    await waitFor(() => expect(runExploreCell).toHaveBeenCalledWith(SESSION_ID, "c0"));
    expect(writeExploreCell).toHaveBeenCalledWith(SESSION_ID, "c0", "value_0 = 99");
    // The queued state came from the run response, which is the slice's one
    // door for it; nothing was written before the runtime answered.
    await waitFor(() =>
      expect(useAppStore.getState().sessions[PATH].cells[0].runState).toBe("queued"),
    );
  });
});

describe("the cell commands (FR-010)", () => {
  it("adds a cell after the one that asked for it", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(2)));
    render(<Shell />);
    fireEvent.click(screen.getByTestId("explore-cell-insert-c0"));
    await waitFor(() => expect(insertExploreCell).toHaveBeenCalledWith(SESSION_ID, "", "c0"));
  });

  it("adds a cell at the end from the shell's own control", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(2)));
    render(<Shell />);
    fireEvent.click(screen.getByTestId("explore-notebook-add-cell"));
    await waitFor(() => expect(insertExploreCell).toHaveBeenCalledWith(SESSION_ID, "", "c1"));
  });

  it("sends the enable toggle and shows the response's answer", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    setExploreCellEnabled.mockResolvedValue(
      cellsResponse([
        { cell_id: "c0", cell_type: "code", source: "value_0 = 0", enabled: false, marks: [] },
      ]),
    );
    render(<Shell />);
    fireEvent.click(screen.getByTestId("explore-cell-enabled-c0"));
    await waitFor(() =>
      expect(setExploreCellEnabled).toHaveBeenCalledWith(SESSION_ID, "c0", false),
    );
    await waitFor(() => expect(useAppStore.getState().sessions[PATH].cells[0].enabled).toBe(false));
  });

  it("refuses delete and move with the reason, because the API has no route", () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    render(<Shell />);
    for (const testId of [
      "explore-cell-delete-c0",
      "explore-cell-move-up-c0",
      "explore-cell-move-down-c0",
    ]) {
      const control = screen.getByTestId(testId) as HTMLButtonElement;
      expect(control.disabled).toBe(true);
      expect(control.title).toContain("no route");
    }
  });

  it("sends run-with-upstream from the mark's control and nothing else", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(2)));
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { marks: { c1: ["out_of_order"] } },
        timestamp: "2026-09-05T12:00:00Z",
      }),
    );
    render(<Shell />);
    fireEvent.click(screen.getByTestId("explore-run-with-upstream-c1"));
    await waitFor(() => expect(runExploreWithUpstream).toHaveBeenCalledWith(SESSION_ID, "c1"));
    expect(runExploreCell).not.toHaveBeenCalled();
  });
});

describe("markdown cells (FR-009)", () => {
  it("renders markdown and edits in place", async () => {
    act(() =>
      useAppStore.getState().applyExploreSession(
        sessionOf(1, {
          cells: [
            {
              cell_id: "m0",
              cell_type: "markdown",
              source: "# Title\n\ntext",
              enabled: true,
              marks: [],
            },
          ],
        }),
      ),
    );
    render(<Shell />);
    const rendered = screen.getByTestId("explore-cell-markdown-m0");
    expect(rendered.querySelector("h1")?.textContent).toBe("Title");

    fireEvent.click(screen.getByTestId("explore-cell-edit-m0"));
    const editor = await screen.findByTestId("monaco-explore-cell/m0");
    expect(editor.getAttribute("data-language")).toBe("markdown");
    fireEvent.change(editor, { target: { value: "# Changed" } });

    fireEvent.click(screen.getByTestId("explore-cell-edit-m0"));
    expect(screen.getByTestId("explore-cell-markdown-m0").querySelector("h1")?.textContent).toBe(
      "Changed",
    );
  });
});

describe("a reload against an unsaved draft (FR-017)", () => {
  it("keeps the draft, marks it conflicting, and re-reads the notebook", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(2)));
    render(<Shell />);
    const editor = await screen.findByTestId("monaco-explore-cell/c0");
    fireEvent.change(editor, { target: { value: "mine, unsaved" } });

    readExploreCells.mockResolvedValue(
      cellsResponse([
        { cell_id: "c0", cell_type: "code", source: "theirs, from disk", enabled: true, marks: [] },
        { cell_id: "c1", cell_type: "code", source: "value_1 = 1", enabled: true, marks: [] },
      ]),
    );
    // `reload_if_changed` publishes exactly this event and carries no cells.
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.analysis_updated",
        session_id: SESSION_ID,
        data: { reason: "external_edit" },
        timestamp: "2026-09-05T12:01:00Z",
      }),
    );

    await waitFor(() => expect(readExploreCells).toHaveBeenCalledWith(SESSION_ID));
    await screen.findByTestId("explore-cell-conflict-c0");
    // The person's text is still there; the file's text is not what is shown.
    expect((screen.getByTestId("monaco-explore-cell/c0") as HTMLTextAreaElement).value).toBe(
      "mine, unsaved",
    );
    expect(useAppStore.getState().sessions[PATH].cells[0].source).toBe("theirs, from disk");
    // Nothing was written back on its own: a conflict is the person's to settle.
    expect(writeExploreCell).not.toHaveBeenCalled();
  });

  it("discards the draft on request and shows what the file says", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    render(<Shell />);
    fireEvent.change(await screen.findByTestId("monaco-explore-cell/c0"), {
      target: { value: "mine, unsaved" },
    });
    readExploreCells.mockResolvedValue(
      cellsResponse([
        { cell_id: "c0", cell_type: "code", source: "theirs, from disk", enabled: true, marks: [] },
      ]),
    );
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.analysis_updated",
        session_id: SESSION_ID,
        data: { reason: "external_edit" },
        timestamp: "2026-09-05T12:01:00Z",
      }),
    );
    await screen.findByTestId("explore-cell-discard-draft-c0");

    fireEvent.click(screen.getByTestId("explore-cell-discard-draft-c0"));
    await waitFor(() =>
      expect((screen.getByTestId("monaco-explore-cell/c0") as HTMLTextAreaElement).value).toBe(
        "theirs, from disk",
      ),
    );
    expect(screen.queryByTestId("explore-cell-conflict-c0")).toBeNull();
  });

  it("writes the draft over the file when the person keeps theirs", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(1)));
    render(<Shell />);
    fireEvent.change(await screen.findByTestId("monaco-explore-cell/c0"), {
      target: { value: "mine, unsaved" },
    });
    readExploreCells.mockResolvedValue(
      cellsResponse([
        { cell_id: "c0", cell_type: "code", source: "theirs, from disk", enabled: true, marks: [] },
      ]),
    );
    act(() =>
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.analysis_updated",
        session_id: SESSION_ID,
        data: { reason: "external_edit" },
        timestamp: "2026-09-05T12:01:00Z",
      }),
    );
    const keep = await screen.findByTestId("explore-cell-keep-draft-c0");

    writeExploreCell.mockResolvedValue(
      cellsResponse([
        { cell_id: "c0", cell_type: "code", source: "mine, unsaved", enabled: true, marks: [] },
      ]),
    );
    fireEvent.click(keep);
    await waitFor(() =>
      expect(writeExploreCell).toHaveBeenCalledWith(SESSION_ID, "c0", "mine, unsaved"),
    );
    await waitFor(() => expect(screen.queryByTestId("explore-cell-conflict-c0")).toBeNull());
  });
});

describe("reconcileDrafts", () => {
  const cell = (cellId: string, source: string) => ({
    cellId,
    cellType: "code",
    source,
    enabled: true,
    outputs: [],
    marks: [],
    outOfOrderReads: [],
    runState: "idle" as const,
    executionCount: null,
    changedNames: [],
    lastEventAt: null,
  });

  it("drops a draft the runtime has caught up with", () => {
    const drafts: CellDrafts = { c0: { text: "saved", base: "old", conflicting: false } };
    expect(reconcileDrafts(drafts, [cell("c0", "saved")])).toEqual({});
  });

  it("keeps a draft the runtime disagrees with and marks it conflicting", () => {
    const drafts: CellDrafts = { c0: { text: "mine", base: "old", conflicting: false } };
    expect(reconcileDrafts(drafts, [cell("c0", "theirs")])).toEqual({
      c0: { text: "mine", base: "theirs", conflicting: true },
    });
  });

  it("leaves an untouched draft alone, object identity and all", () => {
    const drafts: CellDrafts = { c0: { text: "mine", base: "old", conflicting: false } };
    expect(reconcileDrafts(drafts, [cell("c0", "old")])).toBe(drafts);
  });

  it("keeps a draft whose cell is not in the list", () => {
    const drafts: CellDrafts = { gone: { text: "mine", base: "old", conflicting: false } };
    expect(reconcileDrafts(drafts, [cell("c0", "other")])).toBe(drafts);
  });
});
