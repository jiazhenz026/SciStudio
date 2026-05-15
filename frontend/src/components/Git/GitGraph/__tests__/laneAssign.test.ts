/**
 * D39-2.4b tests for `laneAssign.ts`.
 *
 * Covers the fixtures enumerated in the laneAssign.ts file-level docstring:
 * linear history, two-way merge, octopus merge, disconnected roots,
 * empty input, single initial commit, color wrap-around, purity.
 */
import { describe, it, expect } from "vitest";

import { assignLanes, maxLane } from "../laneAssign";
import type { LaneAssignment } from "../laneAssign";
import { PALETTE } from "../colorPalette";
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

const empty: LaneAssignment[] = [];
const singleLane: LaneAssignment[] = [
  { sha: "a", lane: 0, merge_lanes: [], color_index: 0, filtered_out: false },
  { sha: "b", lane: 0, merge_lanes: [], color_index: 0, filtered_out: false },
];
const withMergeLanes: LaneAssignment[] = [
  { sha: "m", lane: 0, merge_lanes: [1, 2], color_index: 0, filtered_out: false },
  { sha: "p", lane: 0, merge_lanes: [], color_index: 0, filtered_out: false },
];

describe("maxLane (pure helper)", () => {
  it("returns -1 for empty input", () => {
    expect(maxLane(empty)).toBe(-1);
  });
  it("returns 0 when every commit lives in lane 0", () => {
    expect(maxLane(singleLane)).toBe(0);
  });
  it("considers merge_lanes when computing the max", () => {
    expect(maxLane(withMergeLanes)).toBe(2);
  });
});

describe("assignLanes (D39-2.4b)", () => {
  it("Fixture A: linear history → all lane 0", () => {
    const commits = [mk("C3", ["C2"]), mk("C2", ["C1"]), mk("C1", [])];
    const r = assignLanes(commits);
    expect(r).toHaveLength(3);
    expect(r[0]).toMatchObject({ sha: "C3", lane: 0, merge_lanes: [], color_index: 0 });
    expect(r[1]).toMatchObject({ sha: "C2", lane: 0, merge_lanes: [] });
    expect(r[2]).toMatchObject({ sha: "C1", lane: 0, merge_lanes: [] });
  });

  it("Fixture B: simple two-way merge", () => {
    const commits = [
      mk("C3", ["C2a", "C2b"]),
      mk("C2a", ["C1"]),
      mk("C2b", ["C1"]),
      mk("C1", []),
    ];
    const r = assignLanes(commits);
    expect(r[0]).toMatchObject({ sha: "C3", lane: 0, merge_lanes: [1] });
    expect(r[1]).toMatchObject({ sha: "C2a", lane: 0, merge_lanes: [] });
    expect(r[2]).toMatchObject({ sha: "C2b", lane: 1, merge_lanes: [] });
    // C1 occupies lane 0 (first findIndex hit), lane 1 is freed when C2b
    // forwards its parent.
    expect(r[3]).toMatchObject({ sha: "C1", lane: 0, merge_lanes: [] });
  });

  it("Fixture C: octopus merge (3 parents)", () => {
    const commits = [
      mk("C2", ["P0", "P1", "P2"]),
      mk("P0", []),
      mk("P1", []),
      mk("P2", []),
    ];
    const r = assignLanes(commits);
    expect(r[0]).toMatchObject({ sha: "C2", lane: 0, merge_lanes: [1, 2] });
    expect(r[1]).toMatchObject({ sha: "P0", lane: 0 });
    expect(r[2]).toMatchObject({ sha: "P1", lane: 1 });
    expect(r[3]).toMatchObject({ sha: "P2", lane: 2 });
  });

  it("Fixture D: two disconnected histories", () => {
    const commits = [
      mk("A2", ["A1"]),
      mk("B2", ["B1"]),
      mk("A1", []),
      mk("B1", []),
    ];
    const r = assignLanes(commits);
    expect(r[0]).toMatchObject({ sha: "A2", lane: 0 });
    expect(r[1]).toMatchObject({ sha: "B2", lane: 1 });
    expect(r[2]).toMatchObject({ sha: "A1", lane: 0 });
    expect(r[3]).toMatchObject({ sha: "B1", lane: 1 });
  });

  it("Fixture E: empty input returns []", () => {
    expect(assignLanes([])).toEqual([]);
  });

  it("Fixture F: single initial commit lands on lane 0", () => {
    const r = assignLanes([mk("C1", [])]);
    expect(r).toEqual([
      { sha: "C1", lane: 0, merge_lanes: [], color_index: 0, filtered_out: false },
    ]);
  });

  it("Fixture G: color_index wraps via modulo on palette length", () => {
    // Build a wide octopus that allocates 12 lanes.
    const parents = Array.from({ length: 12 }, (_, i) => `P${i}`);
    const commits: GitCommit[] = [mk("M", parents)];
    for (const p of parents) commits.push(mk(p, []));
    const r = assignLanes(commits);
    expect(PALETTE.length).toBe(10);
    // Each Pi lands in its own lane i.
    expect(r[1].lane).toBe(0);
    expect(r[1].color_index).toBe(0);
    expect(r[11].lane).toBe(10);
    expect(r[11].color_index).toBe(0); // 10 % 10
    expect(r[12].lane).toBe(11);
    expect(r[12].color_index).toBe(1); // 11 % 10
  });

  it("Fixture H: pure — does not mutate input", () => {
    const commits = [mk("C3", ["C2"]), mk("C2", ["C1"]), mk("C1", [])];
    const snapshot = JSON.parse(JSON.stringify(commits));
    const r1 = assignLanes(commits);
    const r2 = assignLanes(commits);
    expect(commits).toEqual(snapshot);
    expect(r1).toEqual(r2);
  });
});
