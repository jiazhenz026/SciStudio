/**
 * ADR-054 spec 4 (T-014) — the dependency graph view (FR-032).
 *
 * **What jsdom can and cannot prove here.** `@xyflow/react` mounts its nodes
 * from the node array, so a version node either is in the document or is not,
 * and highlight and selection are assertable on the real component. It does
 * **not** mount edges without a measured viewport: the edge renderer needs
 * each endpoint's measured box, and jsdom reports every box as zero. So the
 * edges are asserted where they are actually decided — `buildVersionGraph`,
 * which is the model FR-032 describes, origins included — and the view is
 * asserted to have been handed them, through the count it renders. The
 * browser-level proof that an edge is drawn is spec 4's e2e scenario (T-016).
 * Registered as F-A4-002.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExploreGraphResponse, ExploreSessionResponse } from "../types/api";
import { resetAppStore } from "../testUtils";
import { useAppStore } from "../store";
import type { ExploreSessionState, ExploreTab } from "../store/types";

import { GraphView, buildVersionGraph, connectedRegion, versionNodeId } from "./GraphView";

// ELK lays the graph out asynchronously after first paint. The deterministic
// grid `GraphView` starts from is what these assertions see, and stubbing the
// bundle keeps a real layout engine out of a DOM test.
vi.mock("elkjs/lib/elk.bundled.js", () => ({
  default: class {
    layout() {
      return Promise.resolve({ children: [] });
    }
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-graph";

function tab(): ExploreTab {
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
      { cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] },
      {
        cell_id: "c2",
        cell_type: "code",
        source: "t = df.head()",
        enabled: true,
        marks: ["stale"],
      },
      {
        cell_id: "c3",
        cell_type: "code",
        source: "print(t)",
        enabled: true,
        marks: ["out_of_order"],
      },
      { cell_id: "c4", cell_type: "code", source: "other = 1", enabled: true, marks: [] },
    ],
  };
}

/**
 * The shape `GET .../graph` answers with. `c1` binds `df`, `c2` reads it and
 * binds `t`, `c3` reads `t` and binds nothing — the sink case — and `c4` is a
 * disconnected component so a "connected region" means something.
 */
function graphResponse(): ExploreGraphResponse {
  return {
    session_id: SESSION_ID,
    cells: ["c1", "c2", "c3", "c4"],
    edges: [
      { reader: "c2", definer: "c1", name: "df", origin: "static_assignment" },
      { reader: "c3", definer: "c2", name: "t", origin: "observed_change" },
    ],
    unresolved_reads: [],
    unknown_binding_cells: [],
    changed_sets: { c1: ["df"], c2: ["t"], c3: [], c4: ["other"] },
  };
}

function session(): ExploreSessionState {
  return useAppStore.getState().sessions[PATH];
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  useAppStore.getState().applyExploreSession(sessionResponse());
  useAppStore.getState().applyExploreGraph(SESSION_ID, graphResponse());
});

afterEach(cleanup);

describe("the version graph model (FR-032)", () => {
  it("puts one node per variable version and keeps the reader that binds nothing", () => {
    const model = buildVersionGraph(session().graph!, session().cells);
    expect(model.nodes.map((node) => node.id).sort()).toEqual([
      versionNodeId("c1", "df"),
      versionNodeId("c2", "t"),
      versionNodeId("c3", null),
      versionNodeId("c4", "other"),
    ]);
  });

  it("carries each edge's origin from the analysis", () => {
    const model = buildVersionGraph(session().graph!, session().cells);
    expect(model.edges.map((edge) => [edge.source, edge.target, edge.name, edge.origin])).toEqual([
      [versionNodeId("c1", "df"), versionNodeId("c2", "t"), "df", "static_assignment"],
      [versionNodeId("c2", "t"), versionNodeId("c3", null), "t", "observed_change"],
    ]);
  });

  it("marks a version highlighted when the runtime marked its cell", () => {
    const model = buildVersionGraph(session().graph!, session().cells);
    const byId = new Map(model.nodes.map((node) => [node.id, node.data]));
    expect(byId.get(versionNodeId("c1", "df"))?.highlighted).toBe(false);
    // `stale` on c2 and `out_of_order` on c3 are the two marks FR-032 names.
    expect(byId.get(versionNodeId("c2", "t"))?.highlighted).toBe(true);
    expect(byId.get(versionNodeId("c3", null))?.highlighted).toBe(true);
    expect(byId.get(versionNodeId("c4", "other"))?.highlighted).toBe(false);
  });

  it("reads the region as undirected so upstream is part of it too", () => {
    const model = buildVersionGraph(session().graph!, session().cells);
    expect([...connectedRegion(model, versionNodeId("c3", null))].sort()).toEqual([
      versionNodeId("c1", "df"),
      versionNodeId("c2", "t"),
      versionNodeId("c3", null),
    ]);
    expect([...connectedRegion(model, versionNodeId("c4", "other"))]).toEqual([
      versionNodeId("c4", "other"),
    ]);
  });
});

describe("the rendered view (FR-032)", () => {
  it("renders a node per version and reports the edges it was handed", () => {
    render(<GraphView session={session()} tab={tab()} />);
    expect(screen.getByTestId(`explore-graph-node-${versionNodeId("c1", "df")}`)).toBeTruthy();
    expect(screen.getByTestId(`explore-graph-node-${versionNodeId("c2", "t")}`)).toBeTruthy();
    expect(screen.getByTestId(`explore-graph-node-${versionNodeId("c3", null)}`)).toBeTruthy();
    expect(screen.getByTestId("explore-graph-counts").textContent).toBe(
      "4 versions · 2 dependencies",
    );
  });

  it("highlights the cells the runtime marked stale or out of order", () => {
    render(<GraphView session={session()} tab={tab()} />);
    const stale = screen.getByTestId(`explore-graph-node-${versionNodeId("c2", "t")}`);
    const clean = screen.getByTestId(`explore-graph-node-${versionNodeId("c1", "df")}`);
    expect(stale.getAttribute("data-highlighted")).toBe("true");
    expect(stale.getAttribute("data-marks")).toBe("stale");
    expect(clean.getAttribute("data-highlighted")).toBe("false");
  });

  it("selects the whole connected region a node belongs to", () => {
    render(<GraphView session={session()} tab={tab()} />);
    fireEvent.click(screen.getByTestId(`explore-graph-node-${versionNodeId("c2", "t")}`));

    for (const id of [
      versionNodeId("c1", "df"),
      versionNodeId("c2", "t"),
      versionNodeId("c3", null),
    ]) {
      expect(screen.getByTestId(`explore-graph-node-${id}`).getAttribute("data-selected")).toBe(
        "true",
      );
    }
    // The disconnected component is not part of the region, which is what
    // makes the selection mean anything.
    expect(
      screen
        .getByTestId(`explore-graph-node-${versionNodeId("c4", "other")}`)
        .getAttribute("data-selected"),
    ).toBe("false");
    expect(screen.getByTestId("explore-graph-selection-count").textContent).toBe("3 selected");
  });

  it("says so rather than drawing an empty canvas when no analysis has arrived", () => {
    render(<GraphView session={undefined} tab={tab()} />);
    expect(screen.getByTestId("explore-graph-empty")).toBeTruthy();
    expect(screen.getByTestId("explore-graph-counts").textContent).toBe(
      "0 versions · 0 dependencies",
    );
  });
});
