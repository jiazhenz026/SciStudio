import { beforeEach, describe, expect, it } from "vitest";

import type { WorkflowEdge, WorkflowNode } from "../../types/api";

// The store persists a UI slice via zustand's `persist` middleware, which
// writes through `window.localStorage` on every `setState`. The jsdom
// environment in this worktree does not always expose a working
// `localStorage`, so install a minimal in-memory shim BEFORE importing the
// store module (which subscribes + persists at load time). This isolates the
// layout-batch behavior under test from the persistence env gap.
if (typeof globalThis.localStorage === "undefined" || globalThis.localStorage === null) {
  const backing = new Map<string, string>();
  const shim: Storage = {
    get length() {
      return backing.size;
    },
    clear: () => backing.clear(),
    getItem: (key: string) => (backing.has(key) ? (backing.get(key) as string) : null),
    key: (index: number) => Array.from(backing.keys())[index] ?? null,
    removeItem: (key: string) => void backing.delete(key),
    setItem: (key: string, value: string) => void backing.set(key, String(value)),
  };
  Object.defineProperty(globalThis, "localStorage", { value: shim, configurable: true });
}

const { useAppStore } = await import("../index");

function makeNodes(): WorkflowNode[] {
  return [
    {
      id: "a",
      block_type: "process",
      config: { params: { foo: 1 } },
      execution_mode: "auto",
      layout: { x: 0, y: 0 },
    },
    {
      id: "b",
      block_type: "process",
      config: { params: { bar: 2 } },
      layout: { x: 10, y: 10 },
    },
    {
      id: "c",
      block_type: "io_block",
      config: { params: { direction: "output" } },
      layout: { x: 20, y: 20 },
    },
  ];
}

const EDGES: WorkflowEdge[] = [{ source: "a:out", target: "b:in" }];

function resetStore(): void {
  useAppStore.setState({
    workflowId: "demo",
    workflowName: "demo",
    workflowDescription: "",
    workflowVersion: "1.0.0",
    workflowMetadata: {},
    workflowNodes: makeNodes(),
    workflowEdges: EDGES.map((e) => ({ ...e })),
    workflowDirty: false,
    workflowBaseVersion: 5,
    workflowPendingVersion: 5,
    workflowPendingSourceId: null,
    workflowConflict: null,
    workflowHistory: [],
    workflowFuture: [],
  });
}

describe("updateNodeLayoutBatch (ADR-050 FR-022 / FR-024 / SC-007)", () => {
  beforeEach(() => {
    resetStore();
  });

  it("writes only node.layout and leaves all other node fields untouched", () => {
    const before = makeNodes();
    useAppStore.getState().updateNodeLayoutBatch({
      a: { x: 100, y: 200 },
      b: { x: 300, y: 400 },
    });

    const nodes = useAppStore.getState().workflowNodes;
    const a = nodes.find((n) => n.id === "a")!;
    const b = nodes.find((n) => n.id === "b")!;
    const c = nodes.find((n) => n.id === "c")!;

    // Layout changed for targeted nodes.
    expect(a.layout).toEqual({ x: 100, y: 200 });
    expect(b.layout).toEqual({ x: 300, y: 400 });
    // Untargeted node keeps its original layout (focus-scoped tidy safety).
    expect(c.layout).toEqual(before[2].layout);

    // No id/type/config/execution_mode mutation on any node.
    nodes.forEach((current, idx) => {
      expect(current.id).toBe(before[idx].id);
      expect(current.block_type).toBe(before[idx].block_type);
      expect(current.config).toEqual(before[idx].config);
      expect(current.execution_mode).toEqual(before[idx].execution_mode);
    });

    // Edges are never touched.
    expect(useAppStore.getState().workflowEdges).toEqual(EDGES);
  });

  it("marks the workflow dirty", () => {
    expect(useAppStore.getState().workflowDirty).toBe(false);
    useAppStore.getState().updateNodeLayoutBatch({ a: { x: 1, y: 2 } });
    expect(useAppStore.getState().workflowDirty).toBe(true);
  });

  it("records exactly one history entry per batch (one undo restores all)", () => {
    expect(useAppStore.getState().workflowHistory).toHaveLength(0);

    useAppStore.getState().updateNodeLayoutBatch({
      a: { x: 100, y: 200 },
      b: { x: 300, y: 400 },
      c: { x: 500, y: 600 },
    });

    // A single tidy of three nodes produces one history entry.
    expect(useAppStore.getState().workflowHistory).toHaveLength(1);

    useAppStore.getState().undoWorkflow();

    const nodes = useAppStore.getState().workflowNodes;
    expect(nodes.find((n) => n.id === "a")!.layout).toEqual({ x: 0, y: 0 });
    expect(nodes.find((n) => n.id === "b")!.layout).toEqual({ x: 10, y: 10 });
    expect(nodes.find((n) => n.id === "c")!.layout).toEqual({ x: 20, y: 20 });
  });

  it("is a no-op (no history, not dirty) when no node id matches", () => {
    useAppStore.getState().updateNodeLayoutBatch({ ghost: { x: 9, y: 9 } });
    expect(useAppStore.getState().workflowDirty).toBe(false);
    expect(useAppStore.getState().workflowHistory).toHaveLength(0);
    expect(useAppStore.getState().workflowNodes).toEqual(makeNodes());
  });
});
