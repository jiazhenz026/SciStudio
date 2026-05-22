/**
 * ADR-036 §3.10/§3.11 — TabState discriminated union + file tab actions
 * (Phase 2A — I36a).
 *
 * The skeleton file ``tabState.skeleton.test.ts`` (it.skip stubs) is
 * superseded by these real tests. The skeleton is kept until the audit
 * phase to surface the test plan in code review.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../index";
import type { FileTab, TabState, WorkflowTab } from "../types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectFile: vi.fn(),
      putProjectFile: vi.fn(),
    },
  };
});

import { api } from "../../lib/api";

const getProjectFileMock = vi.mocked(api.getProjectFile);
const putProjectFileMock = vi.mocked(api.putProjectFile);

function resetStore(): void {
  useAppStore.setState({
    tabs: [],
    activeTabId: null,
    workflowId: null,
    workflowName: "Untitled",
    activeBottomTab: "config",
    unreadLogsCount: 0,
    currentProject: {
      id: "proj-1",
      name: "Test",
      description: "",
      path: "/tmp/proj-1",
      last_opened: "2026-01-01",
      current_workflow_id: null,
      workflow_count: 0,
      workflows: [],
    },
  });
}

beforeEach(() => {
  resetStore();
  getProjectFileMock.mockReset();
  putProjectFileMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("TabState discriminated union (ADR-036 §3.10)", () => {
  it("WorkflowTab and FileTab are distinguishable by `kind`", () => {
    const workflow: WorkflowTab = {
      kind: "workflow",
      id: "tab-1",
      workflowId: "wf",
      workflowName: "wf",
      workflowDescription: "",
      workflowVersion: "1.0.0",
      workflowMetadata: {},
      workflowNodes: [],
      workflowEdges: [],
      workflowDirty: false,
      workflowHistory: [],
      workflowFuture: [],
      selectedNodeId: null,
    };
    const file: FileTab = {
      kind: "file",
      id: "file:scratch.py",
      filePath: "scratch.py",
      displayName: "scratch.py",
      language: "python",
      content: "",
      contentLoadedAt: 0,
      dirty: false,
      readOnly: false,
    };

    function describeTab(tab: TabState): string {
      switch (tab.kind) {
        case "workflow":
          return `wf:${tab.workflowName}`;
        case "file":
          return `file:${tab.filePath}`;
        default: {
          // Compile-time exhaustiveness check.
          const _exhaustive: never = tab;
          return _exhaustive;
        }
      }
    }

    expect(describeTab(workflow)).toBe("wf:wf");
    expect(describeTab(file)).toBe("file:scratch.py");
  });
});

describe("openFileTab (ADR-036 §3.10)", () => {
  it("creates a new file tab and focuses it", async () => {
    getProjectFileMock.mockResolvedValueOnce({
      content: "x = 1\n",
      mtime: 1234.5,
      size: 6,
      encoding: "utf-8",
    });

    useAppStore.getState().openFileTab("scratch.py");

    // Placeholder appears immediately.
    let state = useAppStore.getState();
    expect(state.tabs).toHaveLength(1);
    const placeholder = state.tabs[0];
    expect(placeholder.kind).toBe("file");
    if (placeholder.kind !== "file") throw new Error("expected file");
    expect(placeholder.id).toBe("file:scratch.py");
    expect(placeholder.filePath).toBe("scratch.py");
    expect(placeholder.language).toBe("python");
    expect(placeholder.loading).toBe(true);
    expect(state.activeTabId).toBe("file:scratch.py");

    // Wait for the async fetch to resolve.
    await new Promise((r) => setTimeout(r, 0));
    state = useAppStore.getState();
    const populated = state.tabs[0];
    if (populated.kind !== "file") throw new Error("expected file");
    expect(populated.content).toBe("x = 1\n");
    expect(populated.contentLoadedAt).toBe(1234.5);
    expect(populated.loading).toBe(false);
  });

  it("focuses the existing tab on second call to the same path", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });

    useAppStore.getState().openFileTab("a.py");
    await new Promise((r) => setTimeout(r, 0));
    useAppStore.getState().openFileTab("a.py");
    await new Promise((r) => setTimeout(r, 0));

    const state = useAppStore.getState();
    expect(state.tabs).toHaveLength(1);
    expect(getProjectFileMock).toHaveBeenCalledTimes(1);
  });

  it("readOnly=true uses the 'source:' id prefix", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "id: foo\n",
      mtime: 1,
      size: 8,
      encoding: "utf-8",
    });

    useAppStore.getState().openFileTab("workflows/foo.yaml", { readOnly: true });
    const state = useAppStore.getState();
    expect(state.tabs[0].id).toBe("source:workflows/foo.yaml");
  });
});

describe("updateFileTabContent (ADR-036 §3.10)", () => {
  it("flips dirty true on first edit", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });
    useAppStore.getState().openFileTab("a.py");
    await new Promise((r) => setTimeout(r, 0));

    useAppStore.getState().updateFileTabContent("file:a.py", "x = 2\n");
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file");
    expect(tab.content).toBe("x = 2\n");
    expect(tab.dirty).toBe(true);
  });

  it("read-only tab ignores updates", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "id: foo\n",
      mtime: 1,
      size: 8,
      encoding: "utf-8",
    });
    useAppStore.getState().openFileTab("workflows/foo.yaml", { readOnly: true });
    await new Promise((r) => setTimeout(r, 0));

    useAppStore.getState().updateFileTabContent("source:workflows/foo.yaml", "EDITED");
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file");
    expect(tab.content).toBe("id: foo\n");
    expect(tab.dirty).toBe(false);
  });
});

describe("saveFileTab (ADR-036 §3.10)", () => {
  it("clears dirty and updates contentLoadedAt on success", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });
    putProjectFileMock.mockResolvedValue({ mtime: 99.5, size: 7 });

    useAppStore.getState().openFileTab("a.py");
    await new Promise((r) => setTimeout(r, 0));

    useAppStore.getState().updateFileTabContent("file:a.py", "x = 22\n");
    await useAppStore.getState().saveFileTab("file:a.py");

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file");
    expect(tab.dirty).toBe(false);
    expect(tab.contentLoadedAt).toBe(99.5);
    expect(putProjectFileMock).toHaveBeenCalledWith(
      "proj-1",
      "a.py",
      "x = 22\n",
      expect.objectContaining({ sourceId: expect.any(String) }),
    );
  });

  it("read-only tab is a no-op", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "id: foo\n",
      mtime: 1,
      size: 8,
      encoding: "utf-8",
    });
    useAppStore.getState().openFileTab("workflows/foo.yaml", { readOnly: true });
    await new Promise((r) => setTimeout(r, 0));

    await useAppStore.getState().saveFileTab("source:workflows/foo.yaml");
    expect(putProjectFileMock).not.toHaveBeenCalled();
  });

  // Audit 2026-05-14 P1 #1 — regression test.
  // saveFileTab used to snapshot `tab` BEFORE the await, then write
  // `dirty=false` + `contentLoadedAt` based on that stale snapshot
  // post-await, silently overwriting any keystrokes the user made while
  // the PUT was in flight. The fix re-reads the latest tab content after
  // the await and only clears `dirty` if the content has not diverged.
  it("preserves edits made during an in-flight PUT (data-loss race)", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });

    // Stall the PUT until we manually resolve it. This gives us a window
    // to "type" between save start and save end.
    let resolvePut: (value: { mtime: number; size: number }) => void = () => {};
    putProjectFileMock.mockImplementation(
      () => new Promise<{ mtime: number; size: number }>((resolve) => {
        resolvePut = resolve;
      }),
    );

    useAppStore.getState().openFileTab("a.py");
    await new Promise((r) => setTimeout(r, 0));

    // First edit triggers dirty.
    useAppStore.getState().updateFileTabContent("file:a.py", "x = 22\n");
    // Kick off the save (do NOT await it yet — it is mid-flight).
    const savePromise = useAppStore.getState().saveFileTab("file:a.py");
    // Simulate the user typing more while the PUT is in flight.
    useAppStore.getState().updateFileTabContent("file:a.py", "x = 333\n");
    // Now resolve the PUT and let saveFileTab finish.
    resolvePut({ mtime: 99.5, size: 8 });
    await savePromise;

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file");
    // The newer in-memory content MUST survive the save.
    expect(tab.content).toBe("x = 333\n");
    // mtime advances (we did successfully write the older content).
    expect(tab.contentLoadedAt).toBe(99.5);
    // dirty MUST stay true so the next debounce picks up the newer content.
    expect(tab.dirty).toBe(true);
  });

  it("clears dirty when content was NOT touched during the PUT", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });
    putProjectFileMock.mockResolvedValue({ mtime: 42, size: 7 });

    useAppStore.getState().openFileTab("b.py");
    await new Promise((r) => setTimeout(r, 0));
    useAppStore.getState().updateFileTabContent("file:b.py", "y = 2\n");
    await useAppStore.getState().saveFileTab("file:b.py");

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file");
    expect(tab.content).toBe("y = 2\n");
    expect(tab.dirty).toBe(false);
    expect(tab.contentLoadedAt).toBe(42);
  });
});
