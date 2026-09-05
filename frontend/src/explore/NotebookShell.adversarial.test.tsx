/**
 * ADR-054 spec 4 — adversarial tests against the notebook shell and the output
 * renderer (S4-D1, #2253).
 *
 * `NotebookShell.test.tsx` and `OutputRenderer.test.tsx` both pass and both are
 * thorough about the risk §4.5 names — SC-002's editor bound is measured at 12,
 * 60 and 200 cells and the draft survives a swap, so that ground is **not**
 * re-covered here.
 *
 * What both suites share is a premise: every fixture they feed the renderer is
 * a well-formed one. `OutputRenderer.test.tsx` is careful about *semantically*
 * hostile content — an escape that never terminates, an unknown MIME type,
 * HTML that would like to run a script, an output above the truncation bound —
 * and every one of those fixtures is still shaped exactly as nbformat says.
 * FR-011 says the shell renders "cell outputs from the notebook's MIME bundle",
 * and spec §2 says a notebook can be "edited outside SciStudio", which is the
 * one path by which a bundle that is *structurally* wrong reaches this code.
 * A `.ipynb` written by another tool, or hand-edited, is not obliged to be
 * valid, and the shell renders it into the pane a person is looking at.
 *
 * The second premise is the draft's: `reconcileDrafts` deliberately keeps a
 * draft whose cell has left the notebook, and the unmount flush deliberately
 * writes every non-conflicting draft. Each is right on its own; the pair is
 * only ever exercised separately.
 *
 * Findings are recorded in `docs/planning/adr-054-assembly-followups.md` under
 * `### S4-D1 / S5-D1 (adversarial testing)`.
 *
 * **Every `it.fails(...)` in this file is a confirmed defect, not a disabled
 * test.** The assertion inside it is the behaviour the spec asks for, written
 * exactly as it would be written if the implementation had it; `it.fails` is
 * vitest's declaration that the code under test does **not** have it yet. The
 * body still runs and still exercises the real code, so the marker is not
 * silence: the day the defect is fixed, the marked test starts failing and
 * whoever fixed it must delete the marker. Nothing here was weakened to make it
 * pass. The markers exist so the assembly's CI can tell S4-D1's deliberate red
 * from a regression; delete them all with one `sed` to see the raw failures.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState } from "../store/types";
import { resetAppStore } from "../testUtils";
import type { ExploreOutput, ExploreSessionResponse } from "../types/api";

import { NotebookShell } from "./NotebookShell";

vi.mock("@monaco-editor/react", () => ({
  default: (props: {
    path?: string;
    value?: string;
    onChange?: (value: string | undefined) => void;
  }) => (
    <textarea
      data-testid={`monaco-${props.path}`}
      onChange={(event) => props.onChange?.(event.target.value)}
      value={props.value ?? ""}
    />
  ),
}));

const writeExploreCell = vi.fn();
const readExploreCells = vi.fn();

vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    writeExploreCell: (...args: unknown[]) => writeExploreCell(...args),
    insertExploreCell: vi.fn(),
    setExploreCellEnabled: vi.fn(),
    runExploreCell: vi.fn(),
    runExploreWithUpstream: vi.fn(),
    readExploreCells: (...args: unknown[]) => readExploreCells(...args),
  },
}));

const PATH = "explore/adversarial.ipynb";
const SESSION_ID = "sess-adv-shell";

function tab(): ExploreTabState {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: SESSION_ID,
    displayName: "adversarial.ipynb",
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
  };
}

function sessionOf(count: number): ExploreSessionResponse {
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
  };
}

function Shell() {
  const session = useAppStore((state) => state.sessions[PATH]);
  return <NotebookShell session={session} tab={tab()} />;
}

/** Put outputs on a cell the way the runtime does, through the slice. */
function giveOutputs(cellId: string, outputs: unknown[]) {
  act(() => {
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.cell_output",
      session_id: SESSION_ID,
      data: {
        cell_id: cellId,
        status: "error",
        execution_count: 1,
        outputs: outputs as ExploreOutput[],
      },
      timestamp: "2026-09-05T10:00:00Z",
    });
  });
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  writeExploreCell.mockReset();
  readExploreCells.mockReset();
  writeExploreCell.mockResolvedValue({ session_id: SESSION_ID, cells: [] });
  readExploreCells.mockResolvedValue({ session_id: SESSION_ID, cells: [] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

/* -------------------------------------------------------------------------- */
/* FR-011 — "it must degrade, not take the shell down with it"                 */
/* -------------------------------------------------------------------------- */

describe("a structurally malformed output bundle (FR-011)", () => {
  /**
   * Proves: an `error` output whose `traceback` is a **string** rather than a
   * list of strings throws out of `OneOutput` and takes the whole notebook pane
   * with it. There is no error boundary between `OutputRenderer` and
   * `NotebookShell`, so one bad output erases every cell, the toolbar's
   * neighbours in the pane, and the person's unsaved drafts along with them.
   *
   * `OneOutput` reads `(output.traceback ?? []).join("\n")`. `??` guards
   * `null`/`undefined` and nothing else, so a string reaches `.join` and
   * `TypeError: output.traceback.join is not a function` propagates.
   *
   * Why the existing tests did not: `OutputRenderer.test.tsx` has a whole
   * section for hostile *content* ("drops an escape that never terminates",
   * "survives a malformed parameter list without looping", "handles an
   * output_type the shell has never heard of") and every fixture in it is a
   * well-formed nbformat object. The one thing it never varies is the *shape*.
   *
   * It is reachable without a hostile actor: spec §2's own edge case is "the
   * notebook is edited outside SciStudio", `nbformat` does not validate on
   * read here, and a traceback flattened to one string is what several
   * notebook writers emit.
   *
   * Left failing. See F-D1-009.
   */
  it.fails("degrades an error output whose traceback is not a list", () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(3)));
    render(<Shell />);

    giveOutputs("c1", [
      {
        output_type: "error",
        ename: "ValueError",
        evalue: "bad",
        traceback: "Traceback (most recent call last):\n  ValueError: bad",
      },
    ]);

    // The notebook is still on screen — every cell, not only the good ones.
    expect(screen.getByTestId("explore-notebook-cells")).toBeTruthy();
    expect(screen.getByTestId("explore-cell-c0")).toBeTruthy();
    expect(screen.getByTestId("explore-cell-c2")).toBeTruthy();
  });

  /**
   * Proves: a `null` entry in a cell's `outputs` list does the same — a bundle
   * with a hole in it erases the pane.
   *
   * `OutputRenderer` maps over `outputs` and reads `output.output_type` on each
   * entry, so a `null` throws before anything is drawn.
   *
   * Why the existing tests did not: "renders nothing at all for a cell with no
   * outputs" is the only test that varies the *list* rather than its contents,
   * and an empty list is the one degenerate shape that happens to be safe.
   *
   * Left failing, and it shares one repair with the test above: nothing between
   * a cell's outputs and the pane refuses to draw a bundle it cannot read.
   * See F-D1-009.
   */
  it.fails("degrades a bundle with a hole in it", () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(3)));
    render(<Shell />);

    giveOutputs("c1", [null, { output_type: "stream", name: "stdout", text: "ok\n" }]);

    expect(screen.getByTestId("explore-notebook-cells")).toBeTruthy();
    expect(screen.getByTestId("explore-cell-c2")).toBeTruthy();
  });

  /**
   * Proves: a corrupt image payload degrades to a broken image and nothing more
   * — a **negative result**.
   *
   * Why the existing tests did not: "renders an image from the bundle, in
   * preference to its plain text" uses a valid one-pixel PNG. A payload that is
   * not base64 at all is the case a truncated write produces, and the renderer
   * hands it straight to a `data:` URL.
   */
  it("renders a corrupt image payload as an image and nothing worse", () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(2)));
    render(<Shell />);

    giveOutputs("c1", [
      {
        output_type: "display_data",
        data: { "image/png": "%%%% not base 64 at all %%%%" },
        metadata: {},
      },
    ]);

    const image = screen.getByTestId("explore-output-c1-0-image");
    expect(image.getAttribute("src")).toBe("data:image/png;base64,%%%%notbase64atall%%%%");
    expect(screen.getByTestId("explore-cell-c0")).toBeTruthy();
  });
});

/* -------------------------------------------------------------------------- */
/* FR-008, FR-017 — the draft, at the edges of the cell list                   */
/* -------------------------------------------------------------------------- */

describe("a draft whose cell is edited away underneath it", () => {
  /**
   * Proves: an unsaved draft for a cell that the notebook no longer holds is
   * written back to the session API when the shell unmounts — a write to a cell
   * id that does not exist, that the person did not ask for, after they left
   * the tab.
   *
   * The two halves are each deliberate. `reconcileDrafts` keeps a draft whose
   * cell id is gone, documented as "nbformat ids are stable, so a cell that
   * comes back is the same cell". The unmount effect flushes "what the debounce
   * had not sent yet", skipping only conflicting drafts. Neither knows about
   * the other, so the shell's parting act on a tab switch is a `PUT` for a
   * deleted cell.
   *
   * Why the existing tests did not: `reconcileDrafts` is unit-tested for
   * exactly this case ("keeps a draft whose cell is not in the list") as a pure
   * function, with no shell around it and no unmount after it. The unmount
   * flush is not driven by any test at all.
   *
   * Left failing. See F-D1-010.
   */
  it.fails("does not write a draft back to a cell the notebook no longer has", async () => {
    act(() => useAppStore.getState().applyExploreSession(sessionOf(3)));
    const view = render(<Shell />);

    const editor = await screen.findByTestId("monaco-explore-cell/c1");
    fireEvent.change(editor, { target: { value: "value_1 = 'typed but never saved'" } });

    // The notebook is edited outside SciStudio and c1 is gone.
    act(() => {
      useAppStore.getState().applyExploreCells(SESSION_ID, [
        { cell_id: "c0", cell_type: "code", source: "value_0 = 0", enabled: true, marks: [] },
        { cell_id: "c2", cell_type: "code", source: "value_2 = 2", enabled: true, marks: [] },
      ]);
    });
    expect(screen.queryByTestId("explore-cell-c1")).toBeNull();
    writeExploreCell.mockClear();

    // The person switches tabs.
    view.unmount();

    expect(writeExploreCell.mock.calls.map((call) => call[1])).not.toContain("c1");
  });

  /**
   * Proves: a debounced save survives the editor being unmounted by a scroll —
   * a **negative result** for the "edit during a scroll" push.
   *
   * The timers live on the shell rather than on the editor, so a keystroke
   * followed immediately by a scroll still reaches the session API. Had they
   * lived with the editor, the person would lose an edit by scrolling, which is
   * the same failure `drafts`-by-cell-id exists to prevent, one layer down.
   *
   * Why the existing tests did not: "writes one debounced save for a run of
   * keystrokes" runs on a one-cell notebook where nothing can scroll away, and
   * "keeps an unsaved draft when the editor is swapped out and back" asserts on
   * the draft rather than on what reached the API.
   */
  it("still saves an edit whose editor is unmounted before the debounce fires", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    act(() => useAppStore.getState().applyExploreSession(sessionOf(3)));
    render(<Shell />);

    const editor = await screen.findByTestId("monaco-explore-cell/c1");
    fireEvent.change(editor, { target: { value: "value_1 = 'typed then scrolled away'" } });

    // The cell list is replaced, which is what the shell sees when a scroll
    // swaps the editor out: the row survives, the editor does not.
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(writeExploreCell).toHaveBeenCalledWith(
      SESSION_ID,
      "c1",
      "value_1 = 'typed then scrolled away'",
    );
  });
});
