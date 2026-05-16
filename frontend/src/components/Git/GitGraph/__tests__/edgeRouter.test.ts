/**
 * D39-2.4b tests for `edgeRouter.ts`.
 *
 * Coordinate constants (ROW_HEIGHT=22, LANE_PITCH=16, LANE_X_OFFSET=12)
 * are derived from `colorPalette.ts`. The expected path strings hard-code
 * the rendered geometry so visual drift gets caught.
 */
import { describe, it, expect, vi } from "vitest";

import { assignLanes } from "../laneAssign";
import { buildShaIndex, routeEdges, centerOf } from "../edgeRouter";
import type { GitCommit } from "../../../../types/api";

function mk(sha: string, parents: string[] = []): GitCommit {
  return {
    sha,
    short_sha: sha.slice(0, 7),
    parents,
    author_name: "test",
    author_email: "t@e.test",
    author_date: "2026-05-15T00:00:00Z",
    subject: `commit ${sha}`,
    body: "",
    branches: [],
  };
}

describe("buildShaIndex (pure helper)", () => {
  it("returns an empty map for empty input", () => {
    expect(buildShaIndex([]).size).toBe(0);
  });
  it("maps every SHA to its index in source order", () => {
    const commits = [mk("a"), mk("b"), mk("c")];
    const m = buildShaIndex(commits);
    expect(m.get("a")).toBe(0);
    expect(m.get("b")).toBe(1);
    expect(m.get("c")).toBe(2);
    expect(m.has("z")).toBe(false);
  });
});

describe("centerOf (geometry constant)", () => {
  it("(0, 0) → (12, 11)", () => {
    expect(centerOf(0, 0)).toEqual({ x: 12, y: 11 });
  });
  it("(2, 1) → (28, 55)", () => {
    expect(centerOf(2, 1)).toEqual({ x: 28, y: 55 });
  });
});

describe("routeEdges (D39-2.4b)", () => {
  it("Fixture A: linear history → straight vertical paths", () => {
    const commits = [mk("C3", ["C2"]), mk("C2", ["C1"]), mk("C1", [])];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(2);
    expect(edges[0]).toMatchObject({
      child_sha: "C3",
      parent_sha: "C2",
      child_idx: 0,
      parent_idx: 1,
      child_lane: 0,
      parent_lane: 0,
      path: "M 12 11 L 12 33",
      dangling: false,
    });
    expect(edges[1]).toMatchObject({
      child_sha: "C2",
      parent_sha: "C1",
      path: "M 12 33 L 12 55",
    });
  });

  it("Fixture B: fan-out + merge → bezier for lane jumps", () => {
    const commits = [
      mk("C3", ["C2a", "C2b"]),
      mk("C2a", ["C1"]),
      mk("C2b", ["C1"]),
      mk("C1", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(4);
    const byPair = (cs: string, ps: string) =>
      edges.find((e) => e.child_sha === cs && e.parent_sha === ps);

    // C3 → C2a: primary, straight vertical lane 0 → lane 0.
    expect(byPair("C3", "C2a")).toMatchObject({
      child_lane: 0,
      parent_lane: 0,
      path: "M 12 11 L 12 33",
      dangling: false,
    });
    // C3 → C2b: merge fold-in, bezier lane 0 → lane 1.
    // child=centerOf(0,0)=(12,11), parent=centerOf(2,1)=(28,55), midY=33.
    expect(byPair("C3", "C2b")).toMatchObject({
      child_lane: 0,
      parent_lane: 1,
      path: "M 12 11 C 12 33, 28 33, 28 55",
    });
    // Hotfix #994 (supersedes #990): color = max(child_lane, parent_lane).
    // C3(lane 0) → C2b(lane 1): max(0, 1) = 1 (side branch color).
    expect(byPair("C3", "C2b")!.color_index).toBe(1);
    // C2a → C1: primary, straight vertical lane 0 → lane 0.
    expect(byPair("C2a", "C1")).toMatchObject({
      child_lane: 0,
      parent_lane: 0,
      path: "M 12 33 L 12 77",
    });
    // C2b → C1: primary, bezier lane 1 → lane 0.
    // child=centerOf(2,1)=(28,55), parent=centerOf(3,0)=(12,77), midY=66.
    expect(byPair("C2b", "C1")).toMatchObject({
      child_lane: 1,
      parent_lane: 0,
      path: "M 28 55 C 28 66, 12 66, 12 77",
    });
    // Hotfix #994 (#990 follow-up): fork primary edge child_lane=1,
    // parent_lane=0; max(1, 0) = 1 (side branch). Matches dot.
    expect(byPair("C2b", "C1")!.color_index).toBe(1);
  });

  it("Fixture C: dangling parent → stub edge with dangling=true", () => {
    const commits = [mk("C2", ["UNKNOWN_SHA"])];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({
      child_sha: "C2",
      parent_sha: "UNKNOWN_SHA",
      child_idx: 0,
      parent_idx: -1,
      child_lane: 0,
      parent_lane: 0,
      // Stub: child=(12,11), stub goes half a row below → (12, 22).
      path: "M 12 11 L 12 22",
      dangling: true,
    });
  });

  it("Fixture D: octopus merge produces one edge per parent", () => {
    const commits = [
      mk("C", ["P0", "P1", "P2"]),
      mk("P0", []),
      mk("P1", []),
      mk("P2", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(3);
    expect(edges[0].child_lane).toBe(0);
    expect(edges[0].parent_lane).toBe(0);
    // primary edge: straight vertical
    expect(edges[0].path).toBe("M 12 11 L 12 33");
    // merge fold-ins: bezier
    expect(edges[1].parent_lane).toBe(1);
    expect(edges[1].path).toMatch(/^M 12 11 C /);
    expect(edges[2].parent_lane).toBe(2);
    expect(edges[2].path).toMatch(/^M 12 11 C /);
  });

  it("Fixture E: empty input returns []", () => {
    expect(routeEdges([], [])).toEqual([]);
  });

  it("Fixture F (hotfix #994): every edge inherits max(child_lane, parent_lane)", () => {
    // Merge child M on lane 0 with parents A (lane 0) and B (lane 1).
    // Primary edge M→A: max(0,0)=0. Merge edge M→B: max(0,1)=1.
    const commits = [
      mk("M", ["A", "B"]),
      mk("A", []),
      mk("B", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    const primary = edges.find((e) => e.parent_sha === "A")!;
    const merge = edges.find((e) => e.parent_sha === "B")!;
    expect(primary.color_index).toBe(Math.max(primary.child_lane, primary.parent_lane));
    expect(merge.color_index).toBe(Math.max(merge.child_lane, merge.parent_lane));
  });

  it("Fixture H (hotfix #994): octopus/stash — child on trunk, parents on side lanes", () => {
    // Reproduces the Phase 4a Test 6 stash scenario: HEAD on lane 0
    // (the stash commit) has 3 parents, one on each of lanes 0, 1, 2
    // (HEAD-at-stash + index + untracked). Pre-#994 all three edges
    // were stroked with the child's lane (lane 0, blue) — clashing
    // with the lane-1/lane-2 destination dots' colors. Post-#994 each
    // outgoing edge follows the parent's (side-branch) lane color, so
    // dot + curve agree visually.
    const commits = [
      mk("STASH", ["P0", "P1", "P2"]),
      mk("P0", []),
      mk("P1", []),
      mk("P2", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(3);
    for (const e of edges) {
      expect(e.color_index).toBe(Math.max(e.child_lane, e.parent_lane));
    }
    // Sanity: at least one edge crosses lanes (parent on side) and that
    // edge's color is the parent's side-branch lane, not lane 0.
    const crossLane = edges.find((e) => e.parent_lane > 0)!;
    expect(crossLane.color_index).toBe(crossLane.parent_lane);
    expect(crossLane.color_index).not.toBe(0);
  });

  it("Fixture G (hotfix #990/#994): fork edge takes side-branch color end-to-end", () => {
    // Worked example from PR #991: side-branch experiment-1 forks off the
    // main lane. The slant from the side-branch tip back to the common
    // ancestor must be stroked with the SIDE BRANCH's color, not the
    // main lane's color. Pre-#990 this edge was painted with parent_lane
    // (= main = blue) and clashed with the side-branch dot (green).
    const commits = [
      mk("SIDE", ["BASE"]), // side branch tip on lane 1
      mk("MAIN", ["BASE"]), // main tip on lane 0
      mk("BASE", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    const sideFork = edges.find((e) => e.child_sha === "SIDE")!;
    const mainFork = edges.find((e) => e.child_sha === "MAIN")!;
    // At least one of the two forks must be a true cross-lane edge
    // (otherwise the fixture isn't exercising the bug). Per #994 each
    // edge takes `max(child_lane, parent_lane)` — the side-branch lane.
    expect(
      sideFork.child_lane !== sideFork.parent_lane ||
        mainFork.child_lane !== mainFork.parent_lane,
    ).toBe(true);
    expect(sideFork.color_index).toBe(Math.max(sideFork.child_lane, sideFork.parent_lane));
    expect(mainFork.color_index).toBe(Math.max(mainFork.child_lane, mainFork.parent_lane));
  });

  it("self-cycle defensive: drops the edge with a console.warn", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const commits = [mk("X", ["X"])]; // malformed
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    expect(edges).toHaveLength(0);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

