import { describe, expect, it } from "vitest";

import type { WorkflowEdge } from "../../../types/api";
import { computeFocusSet, edgeId, nodeIdOfRef } from "../focusMode";

// Fixture graph (left → right data flow):
//
//   a → b → c
//        ↘ d → e
//   f (isolated)
//
const ALL = ["a", "b", "c", "d", "e", "f"];
const EDGES: WorkflowEdge[] = [
  { source: "a:out", target: "b:in" },
  { source: "b:out", target: "c:in" },
  { source: "b:out", target: "d:in" },
  { source: "d:out", target: "e:in" },
];

describe("nodeIdOfRef", () => {
  it("strips the port suffix from a node:port ref", () => {
    expect(nodeIdOfRef("a:out")).toBe("a");
    expect(nodeIdOfRef("node-123:input_0")).toBe("node-123");
  });

  it("returns the whole ref when there is no port", () => {
    expect(nodeIdOfRef("a")).toBe("a");
  });
});

describe("computeFocusSet — single selection (FR-019)", () => {
  const result = computeFocusSet({ selectedIds: ["b"], allNodeIds: ALL, edges: EDGES });

  it("is active and keeps the selected node visible", () => {
    expect(result.active).toBe(true);
    expect(result.visibleNodeIds.has("b")).toBe(true);
  });

  it("includes immediate upstream and downstream neighbors (one hop)", () => {
    // b's neighbors: a (upstream), c + d (downstream).
    expect(result.visibleNodeIds.has("a")).toBe(true);
    expect(result.visibleNodeIds.has("c")).toBe(true);
    expect(result.visibleNodeIds.has("d")).toBe(true);
  });

  it("dims nodes more than one hop away and isolated nodes", () => {
    // e is two hops from b; f is isolated.
    expect(result.dimmedNodeIds.has("e")).toBe(true);
    expect(result.dimmedNodeIds.has("f")).toBe(true);
    expect(result.hiddenNodeCount).toBe(2);
  });

  it("includes only edges with both endpoints in focus", () => {
    expect(result.visibleEdgeIds.has(edgeId({ source: "a:out", target: "b:in" }))).toBe(true);
    expect(result.visibleEdgeIds.has(edgeId({ source: "b:out", target: "c:in" }))).toBe(true);
    expect(result.visibleEdgeIds.has(edgeId({ source: "b:out", target: "d:in" }))).toBe(true);
    // d→e crosses the focus boundary (e is dimmed) ⇒ dimmed edge.
    expect(result.dimmedEdgeIds.has(edgeId({ source: "d:out", target: "e:in" }))).toBe(true);
  });
});

describe("computeFocusSet — multi-selection induced subgraph (FR-019)", () => {
  it("keeps the selected subgraph plus its boundary neighbors visible", () => {
    // Selecting a and d: a brings b; d brings b (up) and e (down).
    const result = computeFocusSet({ selectedIds: ["a", "d"], allNodeIds: ALL, edges: EDGES });
    expect(result.visibleNodeIds.has("a")).toBe(true);
    expect(result.visibleNodeIds.has("d")).toBe(true);
    expect(result.visibleNodeIds.has("b")).toBe(true); // neighbor of both
    expect(result.visibleNodeIds.has("e")).toBe(true); // downstream of d
    // c is a neighbor of b but b is not selected; b is only reached as a 1-hop
    // neighbor, so c (2 hops from the selection) stays dimmed.
    expect(result.dimmedNodeIds.has("c")).toBe(true);
    expect(result.dimmedNodeIds.has("f")).toBe(true);
  });
});

describe("computeFocusSet — depth control", () => {
  it("depth 0 focuses only the selection", () => {
    const result = computeFocusSet({
      selectedIds: ["b"],
      allNodeIds: ALL,
      edges: EDGES,
      depth: 0,
    });
    expect(result.visibleNodeIds.has("b")).toBe(true);
    expect(result.visibleNodeIds.size).toBe(1);
  });

  it("higher depth expands the visible neighborhood", () => {
    const result = computeFocusSet({
      selectedIds: ["b"],
      allNodeIds: ALL,
      edges: EDGES,
      depth: 2,
    });
    // Two hops from b reaches e (b→d→e).
    expect(result.visibleNodeIds.has("e")).toBe(true);
  });
});

describe("computeFocusSet — empty selection is disabled (FR-018, SC-005)", () => {
  it("reports inactive and leaves everything visible (exit restores)", () => {
    const result = computeFocusSet({ selectedIds: [], allNodeIds: ALL, edges: EDGES });
    expect(result.active).toBe(false);
    expect(result.dimmedNodeIds.size).toBe(0);
    expect(result.hiddenNodeCount).toBe(0);
    // Every node and edge is visible — equivalent to focus mode being off.
    expect(result.visibleNodeIds.size).toBe(ALL.length);
    expect(result.visibleEdgeIds.size).toBe(EDGES.length);
  });

  it("ignores selected ids that are not in the workflow", () => {
    const result = computeFocusSet({ selectedIds: ["ghost"], allNodeIds: ALL, edges: EDGES });
    expect(result.active).toBe(false);
  });
});

describe("computeFocusSet — purity (FR-018)", () => {
  it("does not mutate its inputs", () => {
    const selectedIds = ["b"];
    const allNodeIds = [...ALL];
    const edges = EDGES.map((e) => ({ ...e }));
    const frozenSelected = Object.freeze([...selectedIds]);
    computeFocusSet({ selectedIds: frozenSelected, allNodeIds, edges });
    expect(allNodeIds).toEqual(ALL);
    expect(edges).toHaveLength(EDGES.length);
  });
});
