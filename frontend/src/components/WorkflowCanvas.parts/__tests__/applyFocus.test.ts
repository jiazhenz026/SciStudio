import type { Edge, Node } from "@xyflow/react";
import { describe, expect, it } from "vitest";

import {
  applyFocusToEdges,
  applyFocusToNodes,
  FOCUS_DIMMED_CLASS,
  FOCUS_DIMMED_EDGE_OPACITY,
  FOCUS_DIMMED_NODE_OPACITY,
} from "../applyFocus";
import type { FocusResult } from "../focusMode";

function blockNode(id: string): Node {
  return {
    id,
    type: "block",
    position: { x: 0, y: 0 },
    data: { label: id, blockType: "demo", category: "process", inputPorts: [], outputPorts: [] },
  };
}

function edge(id: string): Edge {
  return { id, source: "a", target: "b" };
}

const INACTIVE: FocusResult = {
  active: false,
  visibleNodeIds: new Set(),
  dimmedNodeIds: new Set(),
  visibleEdgeIds: new Set(),
  dimmedEdgeIds: new Set(),
  hiddenNodeCount: 0,
  hiddenEdgeCount: 0,
};

function activeFocus(dimNodeIds: string[], dimEdgeIds: string[]): FocusResult {
  return {
    active: true,
    visibleNodeIds: new Set(),
    dimmedNodeIds: new Set(dimNodeIds),
    visibleEdgeIds: new Set(),
    dimmedEdgeIds: new Set(dimEdgeIds),
    hiddenNodeCount: dimNodeIds.length,
    hiddenEdgeCount: dimEdgeIds.length,
  };
}

describe("applyFocusToNodes (ADR-050 §3.1 / FR-018)", () => {
  it("returns the array unchanged (same reference) when focus is inactive", () => {
    const nodes = [blockNode("a"), blockNode("b")];
    expect(applyFocusToNodes(nodes, INACTIVE)).toBe(nodes);
  });

  it("dims out-of-focus nodes and leaves in-focus nodes untouched", () => {
    const focused = blockNode("keep");
    const nodes = [focused, blockNode("dim")];
    const result = applyFocusToNodes(nodes, activeFocus(["dim"], []));

    const keep = result.find((n) => n.id === "keep")!;
    const dim = result.find((n) => n.id === "dim")!;
    // In-focus node is referentially identical (no new object allocated).
    expect(keep).toBe(focused);
    expect(keep.className ?? "").not.toContain(FOCUS_DIMMED_CLASS);
    // Out-of-focus node gets the dim class + reduced opacity + no pointer events.
    expect(dim.className).toContain(FOCUS_DIMMED_CLASS);
    expect(dim.style?.opacity).toBe(FOCUS_DIMMED_NODE_OPACITY);
    expect(dim.style?.pointerEvents).toBe("none");
  });

  it("does not mutate the input node objects (FR-018, view-only)", () => {
    const dimmed = blockNode("dim");
    applyFocusToNodes([dimmed], activeFocus(["dim"], []));
    expect(dimmed.className).toBeUndefined();
    expect(dimmed.style).toBeUndefined();
  });

  it("exiting focus (inactive) restores all nodes with no dim props", () => {
    const nodes = [blockNode("a"), blockNode("b")];
    const restored = applyFocusToNodes(nodes, INACTIVE);
    for (const n of restored) {
      expect(n.className ?? "").not.toContain(FOCUS_DIMMED_CLASS);
      expect(n.style?.opacity).toBeUndefined();
    }
  });
});

describe("applyFocusToEdges (ADR-050 §3.1)", () => {
  it("returns edges unchanged when focus is inactive", () => {
    const edges = [edge("e1")];
    expect(applyFocusToEdges(edges, INACTIVE)).toBe(edges);
  });

  it("dims boundary edges and leaves in-focus edges untouched", () => {
    const inFocus = edge("e_keep");
    const result = applyFocusToEdges([inFocus, edge("e_dim")], activeFocus([], ["e_dim"]));
    const keep = result.find((e) => e.id === "e_keep")!;
    const dim = result.find((e) => e.id === "e_dim")!;
    expect(keep).toBe(inFocus);
    expect(dim.style?.opacity).toBe(FOCUS_DIMMED_EDGE_OPACITY);
  });
});
