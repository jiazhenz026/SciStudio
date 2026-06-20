import { beforeEach, describe, expect, it } from "vitest";

import type { LogEntry, WorkflowNode } from "../../types/api";

// The store persists a UI slice through zustand's `persist` middleware, which
// writes through `window.localStorage` at load + on every setState. jsdom in
// this worktree does not always expose a working localStorage, so install an
// in-memory shim BEFORE importing the store module.
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

function noteNode(): WorkflowNode {
  return {
    id: "note-1",
    block_type: "_annotation",
    config: { params: { text: "Note" }, style: { width: 240, height: 120 } },
    layout: { x: 0, y: 0 },
  };
}

function blockNode(): WorkflowNode {
  return {
    id: "blk-1",
    block_type: "process",
    config: { params: {} },
    layout: { x: 10, y: 10 },
  };
}

function logEntry(level: string): LogEntry {
  return { timestamp: "2026-06-20T00:00:00Z", level, message: `${level} message` };
}

describe("updateNodeSize (ux13 — resizable annotation notes)", () => {
  beforeEach(() => {
    useAppStore.setState({
      workflowNodes: [noteNode(), blockNode()],
      workflowDirty: false,
      workflowHistory: [],
      workflowFuture: [],
    });
  });

  it("persists width/height into config.style for an annotation node", () => {
    useAppStore.getState().updateNodeSize("note-1", { width: 360, height: 200 });
    const note = useAppStore.getState().workflowNodes.find((n) => n.id === "note-1");
    expect(note?.config.style).toMatchObject({ width: 360, height: 200 });
    expect(useAppStore.getState().workflowDirty).toBe(true);
  });

  it("ignores non-annotation nodes (no body size written to blocks)", () => {
    useAppStore.getState().updateNodeSize("blk-1", { width: 999, height: 999 });
    const blk = useAppStore.getState().workflowNodes.find((n) => n.id === "blk-1");
    expect(blk?.config.style).toBeUndefined();
    expect(useAppStore.getState().workflowDirty).toBe(false);
  });
});

describe("appendLog unread badge (fb#5 — count errors only)", () => {
  beforeEach(() => {
    useAppStore.setState({ logEntries: [], unreadLogsCount: 0, activeBottomTab: "config" });
  });

  it("bumps the unread count for an error row when not on the Logs tab", () => {
    useAppStore.getState().appendLog(logEntry("error"));
    expect(useAppStore.getState().unreadLogsCount).toBe(1);
  });

  it("does NOT bump for an info row", () => {
    useAppStore.getState().appendLog(logEntry("info"));
    expect(useAppStore.getState().unreadLogsCount).toBe(0);
    // ...but the row is still recorded in the Logs panel.
    expect(useAppStore.getState().logEntries).toHaveLength(1);
  });

  it("does NOT bump when the user is already on the Logs tab", () => {
    useAppStore.setState({ activeBottomTab: "logs" });
    useAppStore.getState().appendLog(logEntry("error"));
    expect(useAppStore.getState().unreadLogsCount).toBe(0);
  });
});
