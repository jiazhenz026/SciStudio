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

describe("computeFocusSet — single selection focuses the whole chain", () => {
  const result = computeFocusSet({ selectedIds: ["b"], allNodeIds: ALL, edges: EDGES });

  it("is active and keeps the selected node visible", () => {
    expect(result.active).toBe(true);
    expect(result.visibleNodeIds.has("b")).toBe(true);
  });

  it("includes every block on the connected chain (full component)", () => {
    // b's component is a→b→c, b→d→e — all reachable along edges.
    expect(result.visibleNodeIds.has("a")).toBe(true);
    expect(result.visibleNodeIds.has("c")).toBe(true);
    expect(result.visibleNodeIds.has("d")).toBe(true);
    expect(result.visibleNodeIds.has("e")).toBe(true);
  });

  it("dims only nodes outside the chain (isolated f)", () => {
    expect(result.visibleNodeIds.has("e")).toBe(true); // on the chain now
    expect(result.dimmedNodeIds.has("f")).toBe(true);
    expect(result.hiddenNodeCount).toBe(1);
  });

  it("highlights every edge within the chain and no others", () => {
    expect(result.visibleEdgeIds.has(edgeId({ source: "a:out", target: "b:in" }))).toBe(true);
    expect(result.visibleEdgeIds.has(edgeId({ source: "b:out", target: "c:in" }))).toBe(true);
    expect(result.visibleEdgeIds.has(edgeId({ source: "b:out", target: "d:in" }))).toBe(true);
    // d→e is on the chain now (e is in focus) ⇒ visible, not dimmed.
    expect(result.visibleEdgeIds.has(edgeId({ source: "d:out", target: "e:in" }))).toBe(true);
    expect(result.dimmedEdgeIds.size).toBe(0);
  });
});

describe("computeFocusSet — multi-selection focuses the whole chain", () => {
  it("keeps the entire connected chain visible regardless of which members are selected", () => {
    const result = computeFocusSet({ selectedIds: ["a", "d"], allNodeIds: ALL, edges: EDGES });
    expect(result.visibleNodeIds.has("a")).toBe(true);
    expect(result.visibleNodeIds.has("b")).toBe(true);
    expect(result.visibleNodeIds.has("c")).toBe(true);
    expect(result.visibleNodeIds.has("d")).toBe(true);
    expect(result.visibleNodeIds.has("e")).toBe(true);
    // f is a separate component (isolated) → dimmed.
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
