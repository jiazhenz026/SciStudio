import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type * as ApiModule from "../../lib/api";
import { useAppStore } from "../../store";
import type { FileTab } from "../../store/types";
import { useWorkflowWebSocket } from "../useWebSocket";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return {
    ...actual,
    consumePendingWorkflowSourceId: vi.fn(() => false),
    api: {
      ...actual.api,
      getWorkflow: vi.fn(),
      getProjectFile: vi.fn(),
    },
  };
});

interface MockSocket {
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: () => void;
  url: string;
}

const createdSockets: MockSocket[] = [];

class MockWebSocket implements MockSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    createdSockets.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({} as CloseEvent);
  }
}

function versionedWorkflow(stateVersion: number, description: string) {
  return {
    id: "demo",
    version: "1.0.0",
    state_version: stateVersion,
    workflow_version: "1.0.0",
    description,
    nodes: [],
    edges: [],
    metadata: {},
  };
}

function fileTab(overrides: Partial<FileTab> = {}): FileTab {
  return {
    kind: "file",
    id: "file:notes.md",
    filePath: "notes.md",
    displayName: "notes.md",
    language: "markdown",
    content: "local\n",
    contentLoadedAt: 1,
    baseVersion: 5,
    pendingVersion: 5,
    pendingSourceId: null,
    conflict: null,
    dirty: false,
    readOnly: false,
    ...overrides,
  };
}

function resetStore(): void {
  useAppStore.setState({
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
    tabs: [],
    activeTabId: null,
    workflowId: null,
    workflowName: "Untitled",
    workflowDescription: "",
    workflowVersion: "1.0.0",
    workflowMetadata: {},
    workflowNodes: [],
    workflowEdges: [],
    workflowDirty: false,
    workflowBaseVersion: null,
    workflowPendingVersion: null,
    workflowPendingSourceId: null,
    workflowConflict: null,
    logEntries: [],
    unreadLogsCount: 0,
    projectTreeRefreshCounter: 0,
  });
}

function pushMessage(message: object): void {
  const sock = createdSockets[0];
  expect(sock).toBeDefined();
  act(() => {
    sock.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  });
}

async function flushAsync(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useWorkflowWebSocket ADR-045 reconcile", () => {
  beforeEach(() => {
    createdSockets.length = 0;
    // @ts-expect-error - install our mock globally
    global.WebSocket = MockWebSocket;
    // @ts-expect-error - MockWebSocket exposes the readyState constants
    global.WebSocket.OPEN = MockWebSocket.OPEN;
    // @ts-expect-error - MockWebSocket exposes the readyState constants
    global.WebSocket.CLOSED = MockWebSocket.CLOSED;
    resetStore();
    vi.mocked(api.getWorkflow).mockReset();
    vi.mocked(api.getProjectFile).mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("drops stale workflow events without fetching or mutating state", () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        workflow_id: "demo",
        entity_class: "workflow",
        entity_id: "demo",
        version: 10,
        source: "agent",
        source_id: "agent-stale",
        kind: "modified",
      },
    });

    expect(api.getWorkflow).not.toHaveBeenCalled();
    expect(useAppStore.getState().workflowDescription).toBe("base");
    expect(useAppStore.getState().workflowBaseVersion).toBe(10);
  });

  it("confirms an autosave echo without overwriting newer local workflow edits", () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    useAppStore.setState({
      workflowDirty: true,
      workflowDescription: "newer local edit",
      workflowBaseVersion: 10,
      workflowPendingVersion: 12,
      workflowPendingSourceId: "workflow-source-1",
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        workflow_id: "demo",
        entity_class: "workflow",
        entity_id: "demo",
        version: 11,
        source: "canvas",
        source_id: "workflow-source-1",
        kind: "modified",
      },
    });

    const state = useAppStore.getState();
    expect(api.getWorkflow).not.toHaveBeenCalled();
    expect(state.workflowDescription).toBe("newer local edit");
    expect(state.workflowBaseVersion).toBe(11);
    expect(state.workflowPendingVersion).toBe(12);
    expect(state.workflowDirty).toBe(true);
  });

  it("refreshes a clean workflow on a newer remote version", async () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    vi.mocked(api.getWorkflow).mockResolvedValueOnce(versionedWorkflow(11, "remote"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        workflow_id: "demo",
        entity_class: "workflow",
        entity_id: "demo",
        version: 11,
        source: "agent",
        source_id: "agent-write",
        kind: "modified",
      },
    });

    await flushAsync();
    expect(api.getWorkflow).toHaveBeenCalledWith("demo");
    expect(useAppStore.getState().workflowDescription).toBe("remote");
    expect(useAppStore.getState().workflowBaseVersion).toBe(11);
  });

  it("refreshes a clean workflow for a source-tagged gitRestore event instead of clearing canvas", async () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    vi.mocked(api.getWorkflow).mockResolvedValueOnce(versionedWorkflow(11, "restored"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        workflow_id: "demo",
        entity_class: "workflow",
        entity_id: "demo",
        version: 11,
        source: "gitRestore",
        source_id: "restore-sha",
        kind: "modified",
      },
    });

    await flushAsync();
    expect(api.getWorkflow).toHaveBeenCalledWith("demo");
    expect(useAppStore.getState().workflowId).toBe("demo");
    expect(useAppStore.getState().workflowDescription).toBe("restored");
    expect(useAppStore.getState().workflowConflict).toBeNull();
  });

  it("records a dirty workflow conflict and preserves local state", async () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    useAppStore.getState().setWorkflowDescription("local dirty");
    vi.mocked(api.getWorkflow).mockResolvedValueOnce(versionedWorkflow(11, "remote"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        workflow_id: "demo",
        entity_class: "workflow",
        entity_id: "demo",
        version: 11,
        source: "agent",
        source_id: "agent-write",
        kind: "modified",
      },
    });

    await flushAsync();
    const state = useAppStore.getState();
    expect(state.workflowDescription).toBe("local dirty");
    expect(state.workflowConflict?.remoteWorkflow?.description).toBe("remote");
    expect(
      state.logEntries.some((entry) => entry.message.includes("local edits were preserved")),
    ).toBe(true);
  });

  it("treats legacy workflow.changed without version as a dirty conflict", async () => {
    useAppStore.getState().setWorkflow(versionedWorkflow(10, "base"));
    useAppStore.getState().setWorkflowDescription("local dirty");
    vi.mocked(api.getWorkflow).mockResolvedValueOnce(versionedWorkflow(11, "legacy remote"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-22T00:00:00Z",
      data: { workflow_id: "demo", kind: "modified", changed_by: "watcher" },
    });

    await flushAsync();
    const state = useAppStore.getState();
    expect(state.workflowDescription).toBe("local dirty");
    expect(state.workflowConflict?.remoteVersion).toBeNull();
    expect(state.workflowConflict?.remoteWorkflow?.description).toBe("legacy remote");
  });

  it("confirms a file.changed self echo by source_id without fetching", () => {
    useAppStore.setState({
      tabs: [
        fileTab({
          dirty: true,
          baseVersion: 5,
          pendingVersion: 6,
          pendingSourceId: "file-source-1",
        }),
      ],
      activeTabId: "file:notes.md",
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "file.changed",
      workflow_id: null,
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        entity_class: "file",
        entity_id: "notes.md",
        path: "notes.md",
        version: 6,
        source: "canvas",
        source_id: "file-source-1",
        kind: "modified",
      },
    });

    expect(api.getProjectFile).not.toHaveBeenCalled();
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.content).toBe("local\n");
    expect(tab.baseVersion).toBe(6);
    expect(tab.pendingVersion).toBe(6);
    expect(tab.pendingSourceId).toBeNull();
    expect(tab.dirty).toBe(false);
  });

  it("adopts a clean file.changed remote version", async () => {
    useAppStore.setState({
      tabs: [fileTab({ dirty: false, baseVersion: 5, pendingVersion: 5 })],
      activeTabId: "file:notes.md",
    });
    vi.mocked(api.getProjectFile).mockResolvedValueOnce({
      content: "remote\n",
      mtime: 9,
      size: 7,
      encoding: "utf-8",
      state_version: 7,
      entity_class: "file",
      entity_id: "notes.md",
      source: null,
      source_id: null,
      kind: "current",
      timestamp: "2026-05-22T00:00:00Z",
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "file.changed",
      workflow_id: null,
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        entity_class: "file",
        entity_id: "notes.md",
        path: "notes.md",
        version: 7,
        source: "external",
        source_id: null,
        kind: "modified",
      },
    });

    await flushAsync();
    expect(api.getProjectFile).toHaveBeenCalledWith("proj-1", "notes.md");
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.content).toBe("remote\n");
    expect(tab.baseVersion).toBe(7);
    expect(tab.pendingVersion).toBe(7);
    expect(tab.dirty).toBe(false);
  });

  it("records a clean file.changed delete conflict without marking the tab dirty", () => {
    useAppStore.setState({
      tabs: [fileTab({ dirty: false, baseVersion: 5, pendingVersion: 5 })],
      activeTabId: "file:notes.md",
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "file.changed",
      workflow_id: null,
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        entity_class: "file",
        entity_id: "notes.md",
        path: "notes.md",
        version: 6,
        source: "external",
        source_id: null,
        kind: "deleted",
      },
    });

    expect(api.getProjectFile).not.toHaveBeenCalled();
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.content).toBe("local\n");
    expect(tab.dirty).toBe(false);
    expect(tab.conflict?.kind).toBe("deleted");
    expect(tab.conflict?.remoteVersion).toBe(6);
  });

  it("records a dirty file conflict and preserves local file content", async () => {
    useAppStore.setState({
      tabs: [fileTab({ dirty: true, pendingVersion: 6 })],
      activeTabId: "file:notes.md",
    });
    vi.mocked(api.getProjectFile).mockResolvedValueOnce({
      content: "remote\n",
      mtime: 9,
      size: 7,
      encoding: "utf-8",
      state_version: 7,
      entity_class: "file",
      entity_id: "notes.md",
      source: null,
      source_id: null,
      kind: "current",
      timestamp: "2026-05-22T00:00:00Z",
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "file.changed",
      workflow_id: null,
      timestamp: "2026-05-22T00:00:00Z",
      data: {
        entity_class: "file",
        entity_id: "notes.md",
        path: "notes.md",
        version: 7,
        source: "external",
        source_id: null,
        kind: "modified",
      },
    });

    await flushAsync();
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.content).toBe("local\n");
    expect(tab.conflict?.remoteContent).toBe("remote\n");
    expect(tab.conflict?.remoteVersion).toBe(7);
  });
});
