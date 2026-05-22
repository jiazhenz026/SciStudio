import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type * as ApiModule from "../../lib/api";
import { useAppStore } from "../index";
import type { FileTab } from "../types";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectFile: vi.fn(),
      putProjectFile: vi.fn(),
    },
    createClientSourceId: vi.fn(() => "file-source-1"),
  };
});

const getProjectFileMock = vi.mocked(api.getProjectFile);
const putProjectFileMock = vi.mocked(api.putProjectFile);

function resetStore(): void {
  useAppStore.setState({
    tabs: [],
    activeTabId: null,
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

describe("tabSlice ADR-045 file version state", () => {
  beforeEach(() => {
    resetStore();
    getProjectFileMock.mockReset();
    putProjectFileMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("loads file state_version as baseVersion while retaining mtime compatibility", async () => {
    getProjectFileMock.mockResolvedValue({
      content: "remote\n",
      mtime: 12,
      size: 7,
      encoding: "utf-8",
      state_version: 42,
      entity_class: "file",
      entity_id: "notes.md",
      source: null,
      source_id: null,
      kind: "current",
      timestamp: "2026-05-22T00:00:00Z",
    });

    useAppStore.getState().openFileTab("notes.md");
    await new Promise((resolve) => setTimeout(resolve, 0));

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.contentLoadedAt).toBe(12);
    expect(tab.baseVersion).toBe(42);
    expect(tab.pendingVersion).toBe(42);
  });

  it("saves with source_id and advances baseVersion from state_version", async () => {
    useAppStore.setState({ tabs: [fileTab({ dirty: true, pendingVersion: 6 })] });
    putProjectFileMock.mockResolvedValue({
      mtime: 13,
      size: 8,
      state_version: 6,
      entity_class: "file",
      entity_id: "notes.md",
      source: "canvas",
      source_id: "file-source-1",
      kind: "modified",
      timestamp: "2026-05-22T00:00:00Z",
    });

    await useAppStore.getState().saveFileTab("file:notes.md");

    expect(putProjectFileMock).toHaveBeenCalledWith("proj-1", "notes.md", "local\n", {
      sourceId: "file-source-1",
    });
    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.dirty).toBe(false);
    expect(tab.baseVersion).toBe(6);
    expect(tab.pendingVersion).toBe(6);
    expect(tab.pendingSourceId).toBeNull();
  });

  it("preserves edits made during a save and keeps pendingVersion newer", async () => {
    useAppStore.setState({ tabs: [fileTab({ dirty: true, pendingVersion: 6 })] });
    let resolvePut: (value: Awaited<ReturnType<typeof api.putProjectFile>>) => void =
      () => {};
    putProjectFileMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePut = resolve;
        }),
    );

    const savePromise = useAppStore.getState().saveFileTab("file:notes.md");
    useAppStore.getState().updateFileTabContent("file:notes.md", "newer\n");
    resolvePut({
      mtime: 13,
      size: 6,
      state_version: 6,
      entity_class: "file",
      entity_id: "notes.md",
      source: "canvas",
      source_id: "file-source-1",
      kind: "modified",
      timestamp: "2026-05-22T00:00:00Z",
    });
    await savePromise;

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.content).toBe("newer\n");
    expect(tab.dirty).toBe(true);
    expect(tab.baseVersion).toBe(6);
    expect(tab.pendingVersion).toBeGreaterThan(6);
  });

  it("records a clean remote file delete without marking the tab dirty", () => {
    useAppStore.setState({ tabs: [fileTab({ dirty: false, baseVersion: 5, pendingVersion: 5 })] });

    useAppStore.getState().markFileRemoteConflict("file:notes.md", {
      entityClass: "file",
      entityId: "notes.md",
      kind: "deleted",
      source: "external",
      sourceId: null,
      baseVersion: 5,
      pendingVersion: 5,
      remoteVersion: 6,
      detectedAt: "2026-05-22T00:00:00Z",
      message: "File 'notes.md' was deleted remotely; local tab content was left unchanged.",
    });

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.dirty).toBe(false);
    expect(tab.conflict?.kind).toBe("deleted");
    expect(tab.content).toBe("local\n");
  });

  it("records a dirty remote file delete as a conflict while preserving local content", () => {
    useAppStore.setState({ tabs: [fileTab({ dirty: true, baseVersion: 5, pendingVersion: 6 })] });

    useAppStore.getState().markFileRemoteConflict("file:notes.md", {
      entityClass: "file",
      entityId: "notes.md",
      kind: "deleted",
      source: "external",
      sourceId: null,
      baseVersion: 5,
      pendingVersion: 6,
      remoteVersion: 7,
      detectedAt: "2026-05-22T00:00:00Z",
      message: "File 'notes.md' was deleted remotely; local edits were preserved.",
    });

    const tab = useAppStore.getState().tabs[0];
    if (tab.kind !== "file") throw new Error("expected file tab");
    expect(tab.dirty).toBe(true);
    expect(tab.conflict?.remoteVersion).toBe(7);
    expect(tab.content).toBe("local\n");
  });
});
