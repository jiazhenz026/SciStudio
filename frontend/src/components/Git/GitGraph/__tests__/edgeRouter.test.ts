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
    // Merge edge → color inherits child lane (0).
    expect(byPair("C3", "C2b")!.color_index).toBe(0);
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
    // Primary edge → color inherits parent lane (0).
    expect(byPair("C2b", "C1")!.color_index).toBe(0);
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

  it("Fixture F: primary inherits parent_lane; merge inherits child_lane", () => {
    // Build a fixture where the merge child sits on lane 0 and its
    // merge parent sits on lane 1. Primary edge: lane 0 → lane 0 (parent
    // also lane 0 because of recycling); merge edge: lane 0 → lane 1.
    const commits = [
      mk("M", ["A", "B"]),
      mk("A", []),
      mk("B", []),
    ];
    const assignments = assignLanes(commits);
    const edges = routeEdges(assignments, commits);
    const primary = edges.find((e) => e.parent_sha === "A")!;
    const merge = edges.find((e) => e.parent_sha === "B")!;
    // Primary edge inherits parent lane.
    expect(primary.color_index).toBe(primary.parent_lane);
    // Merge edge inherits child lane.
    expect(merge.color_index).toBe(merge.child_lane);
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

