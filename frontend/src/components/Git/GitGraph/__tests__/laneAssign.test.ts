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
    const commits = [mk("C3", ["C2a", "C2b"]), mk("C2a", ["C1"]), mk("C2b", ["C1"]), mk("C1", [])];
    const r = assignLanes(commits);
    expect(r[0]).toMatchObject({ sha: "C3", lane: 0, merge_lanes: [1] });
    expect(r[1]).toMatchObject({ sha: "C2a", lane: 0, merge_lanes: [] });
    expect(r[2]).toMatchObject({ sha: "C2b", lane: 1, merge_lanes: [] });
    // C1 occupies lane 0 (first findIndex hit), lane 1 is freed when C2b
    // forwards its parent.
    expect(r[3]).toMatchObject({ sha: "C1", lane: 0, merge_lanes: [] });
  });

  it("Fixture C: octopus merge (3 parents)", () => {
    const commits = [mk("C2", ["P0", "P1", "P2"]), mk("P0", []), mk("P1", []), mk("P2", [])];
    const r = assignLanes(commits);
    expect(r[0]).toMatchObject({ sha: "C2", lane: 0, merge_lanes: [1, 2] });
    expect(r[1]).toMatchObject({ sha: "P0", lane: 0 });
    expect(r[2]).toMatchObject({ sha: "P1", lane: 1 });
    expect(r[3]).toMatchObject({ sha: "P2", lane: 2 });
  });

  it("Fixture D: two disconnected histories", () => {
    const commits = [mk("A2", ["A1"]), mk("B2", ["B1"]), mk("A1", []), mk("B1", [])];
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

  // Hotfix #1002 regression coverage — the BFS-greedy precursor produced
  // maxLane ~= 30 here because every merged-and-deleted feature branch
  // held a lane slot open all the way to repo root. The DFS-chain +
  // per-color recycle algorithm reuses each slot the moment its branch
  // ends, so the slot count collapses to "branches alive in any window".
  it("Fixture I (#1002): long history with sequential merges compacts to active branches", () => {
    // Synthesize a 100-commit history. Trunk M_k commits run k=0..N_M-1
    // newest-first. For each of N_BRANCHES feature branches, branch B_b
    // has 3 unique commits B_b_2, B_b_1, B_b_0 (newest first) and merges
    // into the trunk at some merge commit. After branch b merges, its
    // lane should become recyclable for branch b+1 because the unique
    // commits are 3 rows of contiguous DFS chain and the branch ends
    // before branch b+1 starts.
    const N_BRANCHES = 30;
    const commits: GitCommit[] = [];
    // Build newest-first. We interleave: merge commit M_b, then trunk
    // commit T_b (the merge's first parent), then 3 feature commits
    // B_b_2, B_b_1, B_b_0 (B_b_0's parent is T_{b+1} — i.e. the previous
    // trunk commit).
    for (let b = 0; b < N_BRANCHES; b++) {
      const merge = `M${b}`;
      const trunk = `T${b}`;
      const nextTrunk = `T${b + 1}`;
      const feat2 = `B${b}_2`;
      const feat1 = `B${b}_1`;
      const feat0 = `B${b}_0`;
      // Merge commit on trunk: parents [T_b (first), B_b_2 (merge fold-in)]
      commits.push(mk(merge, [trunk, feat2]));
      // Trunk commit: parent is the NEXT merge commit (older)
      // For the last branch, parent is the root.
      const trunkParent = b === N_BRANCHES - 1 ? "ROOT" : `M${b + 1}`;
      commits.push(mk(trunk, [trunkParent]));
      // Feature commits, newest first, chain down to nextTrunk
      commits.push(mk(feat2, [feat1]));
      commits.push(mk(feat1, [feat0]));
      commits.push(mk(feat0, [nextTrunk]));
    }
    // Root commit
    commits.push(mk("ROOT", []));
    // Sanity: we built 30 * 5 + 1 = 151 commits
    expect(commits.length).toBe(N_BRANCHES * 5 + 1);

    const r = assignLanes(commits);
    expect(r).toHaveLength(commits.length);
    // The pre-fix BFS-greedy algorithm produces maxLane = N_BRANCHES = 30.
    // The DFS-chain + recycle algorithm produces maxLane <= 10.
    // (Empirically, with sequential merges where each branch ends before
    // the next begins, maxLane should be 1: trunk + one side lane that
    // recycles. The <= 10 bound gives headroom for window overlaps in
    // case the topology induces brief 2-3-way overlap.)
    expect(maxLane(r)).toBeLessThanOrEqual(10);
  });

  // Hotfix #1002 regression coverage — chain break behaviour. A branch
  // whose 2 unique commits join trunk via a merge should occupy a lane
  // SPAN of exactly 2 rows (the unique commits), NOT extend all the way
  // down through trunk to repo root.
  it("Fixture J (#1002): branch chain breaks on already-laned commit", () => {
    // Topology (newest first):
    //   M    (merge: parents [T1, B1])
    //   T1   (trunk:  parents [T0])
    //   B1   (feat:   parents [B0])
    //   B0   (feat:   parents [T0])
    //   T0   (trunk:  parents [ROOT])
    //   ROOT (root:   parents [])
    const commits = [
      mk("M", ["T1", "B1"]),
      mk("T1", ["T0"]),
      mk("B1", ["B0"]),
      mk("B0", ["T0"]),
      mk("T0", ["ROOT"]),
      mk("ROOT", []),
    ];
    const r = assignLanes(commits);

    // The feature branch (B1, B0) should occupy a single side lane.
    // B0's parent is T0, which is already on the trunk lane — that's the
    // chain break point. So the side branch's lane span = exactly the
    // count of unique commits = 2 (B1 and B0).
    const b1 = r.find((a) => a.sha === "B1")!;
    const b0 = r.find((a) => a.sha === "B0")!;
    const t0 = r.find((a) => a.sha === "T0")!;
    expect(b1.lane).toBe(b0.lane);
    expect(b1.lane).not.toBe(t0.lane);

    // The number of rows occupying the side branch's lane is exactly 2.
    const sideLane = b1.lane;
    const sideLaneSpan = r.filter((a) => a.lane === sideLane).length;
    expect(sideLaneSpan).toBe(2);
  });
});
