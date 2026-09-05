/**
 * ADR-054 spec 4 (T-012, T-015) — what the Explore tab adds to the palette
 * (FR-029, FR-031).
 *
 * Kept beside `BlockPalette.test.tsx` rather than inside it: that suite is the
 * palette's own contract and runs on fake timers throughout, and folding a
 * store-driven, fetch-driven surface into it would make both harder to read.
 *
 * The second half of FR-031 gets as much attention as the first: with no
 * Explore tab active the card must be **exactly** what it was, which for a
 * non-promotable block means no action row at all — the popover draws a
 * hairline above whatever it is given, so an element that renders nothing
 * would still change the card.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../testUtils";
import { useAppStore } from "../store";
import type { ExploreSessionEventMessage, ExploreSessionResponse } from "../types/api";
import type { BlockSummary, ExploreCellsResponse } from "../types/api";

import { BlockPalette } from "./BlockPalette";
import { blockCallSource, callTargetName } from "./BlockPalette.parts/exploreCall";

const insertExploreCell = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    insertExploreCell: (...args: unknown[]) => insertExploreCell(...args),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-palette";

function port(name: string, direction: "input" | "output"): BlockSummary["input_ports"][number] {
  return {
    name,
    direction,
    accepted_types: ["Image"],
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

const cellpose: BlockSummary = {
  name: "Cellpose Segment",
  type_name: "imaging.cellpose_segment",
  base_category: "process",
  subcategory: "",
  description: "Run Cellpose on an image.",
  version: "0.1.0",
  input_ports: [port("image", "input")],
  output_ports: [port("masks", "output")],
};

const onReload = vi.fn();
const defaultProps = {
  blocks: [cellpose],
  search: "",
  collapsed: false,
  onSearch: vi.fn(),
  onReload,
  onAddBlock: vi.fn(),
};

function sessionResponse(): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: true,
    needs_restart: false,
    current_cell: "c2",
    notebook_commit: null,
    bound_run: null,
    cells: [
      { cell_id: "c1", cell_type: "code", source: "img = load()", enabled: true, marks: [] },
      { cell_id: "c2", cell_type: "code", source: "img.shape", enabled: true, marks: [] },
    ],
  };
}

function cellsResponse(): ExploreCellsResponse {
  return {
    session_id: SESSION_ID,
    cells: [
      { cell_id: "c1", cell_type: "code", source: "img = load()", enabled: true, marks: [] },
      { cell_id: "c2", cell_type: "code", source: "img.shape", enabled: true, marks: [] },
      {
        cell_id: "c3",
        cell_type: "code",
        source: blockCallSource(cellpose),
        enabled: true,
        marks: ["never_run"],
      },
    ],
  };
}

/** Open an Explore tab and make it the active one. */
function activateExploreTab() {
  useAppStore.getState().applyExploreSession(sessionResponse());
  useAppStore.setState({
    tabs: [
      {
        kind: "explore",
        id: `explore:${PATH}`,
        notebookPath: PATH,
        sessionId: SESSION_ID,
        displayName: "analysis.ipynb",
        mode: "session",
        boundRunId: null,
        pauseNodeId: null,
        notebookVisible: true,
      },
    ],
    activeTabId: `explore:${PATH}`,
  });
}

function openCard() {
  fireEvent.mouseEnter(screen.getAllByTestId("palette-block-tile")[0]);
  act(() => {
    vi.advanceTimersByTime(200);
  });
  return screen.getByTestId("block-detail-popover");
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({
    sessions: {},
    sessionPathById: {},
    pendingExploreEvents: {},
    tabs: [],
    activeTabId: null,
  });
  onReload.mockReset();
  insertExploreCell.mockReset();
  insertExploreCell.mockResolvedValue(cellsResponse());
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("the insert-call action (FR-031)", () => {
  it("inserts a call after the current cell while an Explore tab is active", async () => {
    vi.useFakeTimers();
    activateExploreTab();
    render(<BlockPalette {...defaultProps} />);

    const card = openCard();
    fireEvent.click(within(card).getByTestId("palette-insert-block-call"));

    vi.useRealTimers();
    await waitFor(() =>
      expect(insertExploreCell).toHaveBeenCalledWith(
        SESSION_ID,
        'masks = blocks.run("imaging.cellpose_segment", image=...)',
        // FR-031's "after the current cell" — the session's own `current_cell`.
        "c2",
      ),
    );

    // The cell the shell shows is the one the response carried, not one this
    // component invented from the request it sent (FR-034).
    await waitFor(() =>
      expect(useAppStore.getState().sessions[PATH].cells.map((cell) => cell.cellId)).toEqual([
        "c1",
        "c2",
        "c3",
      ]),
    );
  });

  it("leaves the card exactly as it was when no Explore tab is active", () => {
    vi.useFakeTimers();
    render(<BlockPalette {...defaultProps} />);
    const card = openCard();

    expect(within(card).queryByTestId("palette-insert-block-call")).toBeNull();
    // `cellpose` is a built-in, so it has no promote action either: with no
    // Explore tab the card carries no action row at all.
    expect(card.querySelectorAll("button")).toHaveLength(0);
  });
});

describe("the call template", () => {
  it("names the result after the one output port and passes every input by name", () => {
    expect(callTargetName(cellpose)).toBe("masks");
    expect(blockCallSource(cellpose)).toBe(
      'masks = blocks.run("imaging.cellpose_segment", image=...)',
    );
  });

  it("binds `result` when the block declares anything but one output", () => {
    const two: BlockSummary = {
      ...cellpose,
      output_ports: [port("masks", "output"), port("flows", "output")],
    };
    expect(blockCallSource(two)).toBe('result = blocks.run("imaging.cellpose_segment", image=...)');
    expect(blockCallSource({ ...cellpose, output_ports: [], input_ports: [] })).toBe(
      'result = blocks.run("imaging.cellpose_segment")',
    );
  });
});

describe("the packaged event (FR-029)", () => {
  function packagedEvent(blockName: string, commit: string): ExploreSessionEventMessage {
    return {
      type: "explore.packaged",
      session_id: SESSION_ID,
      data: {
        block_name: blockName,
        class_name: "SegmentCells",
        declaration_path: "blocks/segment_cells.py",
        notebook_path: PATH,
        notebook_commit: commit,
        cells: ["c1", "c2"],
        on_new_input: "replay",
      },
      timestamp: "2026-01-01T00:00:00Z",
    };
  }

  it("refreshes the palette so the new block appears", async () => {
    activateExploreTab();
    const { rerender } = render(<BlockPalette {...defaultProps} />);
    // The mount reload every visit already performs (#2151).
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));

    act(() => {
      useAppStore.getState().applyExploreSessionEvent(packagedEvent("Segment Cells", "sha1"));
    });
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));

    // The re-fetch is what puts the block on screen; the palette invents no row.
    const packaged: BlockSummary = {
      ...cellpose,
      name: "Segment Cells",
      type_name: "segment_cells",
    };
    rerender(<BlockPalette {...defaultProps} blocks={[cellpose, packaged]} />);
    expect(screen.getByText("Segment Cells")).toBeTruthy();
  });

  it("does not refresh for a cell run, or twice for the same packaged block", async () => {
    activateExploreTab();
    render(<BlockPalette {...defaultProps} />);
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));

    act(() => {
      useAppStore.getState().applyExploreSessionEvent({
        type: "explore.cell_state",
        session_id: SESSION_ID,
        data: { cell_id: "c1", state: "running" },
        timestamp: "2026-01-01T00:00:01Z",
      });
    });
    expect(onReload).toHaveBeenCalledTimes(1);

    act(() => {
      useAppStore.getState().applyExploreSessionEvent(packagedEvent("Segment Cells", "sha1"));
    });
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));

    act(() => {
      useAppStore.getState().applyExploreSessionEvent(packagedEvent("Segment Cells", "sha1"));
    });
    expect(onReload).toHaveBeenCalledTimes(2);
  });
});
