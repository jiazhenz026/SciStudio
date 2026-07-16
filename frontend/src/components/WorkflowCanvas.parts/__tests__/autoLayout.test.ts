import { describe, expect, it } from "vitest";

import type { WorkflowEdge, WorkflowNode } from "../../../types/api";
import { computeAutoLayout } from "../autoLayout";
import { NODE_SIZE } from "../layoutConstants";

function node(id: string): WorkflowNode {
  return { id, block_type: "process", config: { params: {} } };
}

// Linear DAG: a → b → c → d
const LINEAR_NODES = ["a", "b", "c", "d"].map(node);
const LINEAR_EDGES: WorkflowEdge[] = [
  { source: "a:out", target: "b:in" },
  { source: "b:out", target: "c:in" },
  { source: "c:out", target: "d:in" },
];

// Diamond DAG: a → b, a → c, b → d, c → d
const DIAMOND_NODES = ["a", "b", "c", "d"].map(node);
const DIAMOND_EDGES: WorkflowEdge[] = [
  { source: "a:out", target: "b:in" },
  { source: "a:out", target: "c:in" },
  { source: "b:out", target: "d:in" },
  { source: "c:out", target: "d:in" },
];

describe("computeAutoLayout — basic shape", () => {
  it("returns a position for every node", async () => {
    const positions = await computeAutoLayout({ nodes: LINEAR_NODES, edges: LINEAR_EDGES });
    expect(Object.keys(positions).sort()).toEqual(["a", "b", "c", "d"]);
    for (const id of ["a", "b", "c", "d"]) {
      expect(typeof positions[id].x).toBe("number");
      expect(typeof positions[id].y).toBe("number");
      expect(Number.isInteger(positions[id].x)).toBe(true);
      expect(Number.isInteger(positions[id].y)).toBe(true);
    }
  });

  it("lays out a linear DAG left-to-right by data flow", async () => {
    const positions = await computeAutoLayout({ nodes: LINEAR_NODES, edges: LINEAR_EDGES });
    // Each downstream node sits in a later (further-right) layer.
    expect(positions.a.x).toBeLessThan(positions.b.x);
    expect(positions.b.x).toBeLessThan(positions.c.x);
    expect(positions.c.x).toBeLessThan(positions.d.x);
    // Adjacent layers are at least one node-width apart.
    expect(positions.b.x - positions.a.x).toBeGreaterThanOrEqual(NODE_SIZE);
  });

  it("places a diamond's branches in the same middle layer", async () => {
    const positions = await computeAutoLayout({ nodes: DIAMOND_NODES, edges: DIAMOND_EDGES });
    expect(positions.a.x).toBeLessThan(positions.b.x);
    expect(positions.a.x).toBeLessThan(positions.c.x);
    expect(positions.b.x).toBeLessThan(positions.d.x);
    expect(positions.c.x).toBeLessThan(positions.d.x);
    // b and c share a layer ⇒ same x, different y.
    expect(positions.b.x).toBe(positions.c.x);
    expect(positions.b.y).not.toBe(positions.c.y);
  });
});

describe("computeAutoLayout — determinism (SC-006)", () => {
  it("produces identical output across repeated runs on the same input", async () => {
    const first = await computeAutoLayout({ nodes: DIAMOND_NODES, edges: DIAMOND_EDGES });
    const second = await computeAutoLayout({ nodes: DIAMOND_NODES, edges: DIAMOND_EDGES });
    expect(second).toEqual(first);
  });

  it("is stable regardless of input node/edge ordering", async () => {
    const ordered = await computeAutoLayout({ nodes: DIAMOND_NODES, edges: DIAMOND_EDGES });
    const shuffled = await computeAutoLayout({
      nodes: [...DIAMOND_NODES].reverse(),
      edges: [...DIAMOND_EDGES].reverse(),
    });
    expect(shuffled).toEqual(ordered);
  });
});

describe("computeAutoLayout — robustness", () => {
  it("handles cycles without throwing", async () => {
    const nodes = ["a", "b", "c"].map(node);
    const edges: WorkflowEdge[] = [
      { source: "a:out", target: "b:in" },
      { source: "b:out", target: "c:in" },
      { source: "c:out", target: "a:in" }, // back-edge → cycle
    ];
    const positions = await computeAutoLayout({ nodes, edges });
    expect(Object.keys(positions).sort()).toEqual(["a", "b", "c"]);
  });

  it("handles disconnected components without throwing", async () => {
    const nodes = ["a", "b", "x", "y"].map(node);
    const edges: WorkflowEdge[] = [
      { source: "a:out", target: "b:in" },
      { source: "x:out", target: "y:in" },
    ];
    const positions = await computeAutoLayout({ nodes, edges });
    expect(Object.keys(positions).sort()).toEqual(["a", "b", "x", "y"]);
  });

  it("ignores self-loops and lays out a single node", async () => {
    const nodes = [node("solo")];
    const edges: WorkflowEdge[] = [{ source: "solo:out", target: "solo:in" }];
    const positions = await computeAutoLayout({ nodes, edges });
    expect(Object.keys(positions)).toEqual(["solo"]);
  });

  it("returns an empty map for an empty graph", async () => {
    const positions = await computeAutoLayout({ nodes: [], edges: [] });
    expect(positions).toEqual({});
  });
});

describe("computeAutoLayout — scope (focus-scoped tidy, ADR-050 §3.2)", () => {
  it("lays out only the scoped nodes and omits the rest", async () => {
    const positions = await computeAutoLayout({
      nodes: LINEAR_NODES,
      edges: LINEAR_EDGES,
      scopeNodeIds: new Set(["b", "c"]),
    });
    expect(Object.keys(positions).sort()).toEqual(["b", "c"]);
    expect(positions.a).toBeUndefined();
    expect(positions.d).toBeUndefined();
    // The single in-scope edge b→c still flows left-to-right.
    expect(positions.b.x).toBeLessThan(positions.c.x);
  });

  it("drops edges that leave the scope", async () => {
    // Scope a single node; its connecting edge has an out-of-scope endpoint.
    const positions = await computeAutoLayout({
      nodes: LINEAR_NODES,
      edges: LINEAR_EDGES,
      scopeNodeIds: new Set(["b"]),
    });
    expect(Object.keys(positions)).toEqual(["b"]);
  });
});

describe("computeAutoLayout — annotations are not laid out (#1954)", () => {
  function annotation(id: string): WorkflowNode {
    return {
      id,
      block_type: "_annotation",
      config: { params: { text: "Note" }, style: { width: 240, height: 120 } },
      layout: { x: 111, y: 222 },
    };
  }

  it("omits annotation nodes from the output so their positions stay pinned", async () => {
    const positions = await computeAutoLayout({
      nodes: [...LINEAR_NODES, annotation("note-1")],
      edges: LINEAR_EDGES,
    });
    // The note is never assigned a layout position; the caller leaves its
    // persisted `layout` untouched.
    expect(positions["note-1"]).toBeUndefined();
    expect(Object.keys(positions).sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("does not let an annotation perturb the layout of real nodes", async () => {
    const withoutNote = await computeAutoLayout({ nodes: LINEAR_NODES, edges: LINEAR_EDGES });
    const withNote = await computeAutoLayout({
      nodes: [...LINEAR_NODES, annotation("note-1")],
      edges: LINEAR_EDGES,
    });
    expect(withNote).toEqual(withoutNote);
  });

  it("returns an empty map when the graph is annotations only", async () => {
    const positions = await computeAutoLayout({
      nodes: [annotation("note-1"), annotation("note-2")],
      edges: [],
    });
    expect(positions).toEqual({});
  });

  it("excludes an annotation even when it is inside the focus scope", async () => {
    const positions = await computeAutoLayout({
      nodes: [...LINEAR_NODES, annotation("note-1")],
      edges: LINEAR_EDGES,
      scopeNodeIds: new Set(["b", "note-1"]),
    });
    expect(Object.keys(positions).sort()).toEqual(["b"]);
    expect(positions["note-1"]).toBeUndefined();
  });
});
