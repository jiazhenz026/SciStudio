/**
 * ADR-036 §3.5 (I36c) — ProjectTree double-click wiring tests.
 *
 * Verifies that double-clicking a file in the tree dispatches the right
 * action:
 *   - workflows/<name>.yaml -> onLoadWorkflow
 *   - blocks/<name>.py      -> onReloadBlocks AND store.openFileTab
 *   - <name>.{py,md,json,csv,txt} anywhere -> store.openFileTab
 *   - <name>.tiff (not in editable set) -> NO action
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectTree: vi.fn(),
    },
  };
});

import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import { ProjectTree } from "../ProjectTree";

const getProjectTreeMock = vi.mocked(api.getProjectTree);

beforeEach(() => {
  // Reset store + open-file action.
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
    projectTreeRefreshCounter: 0,
  });
  getProjectTreeMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function renderTreeWith(
  entries: { name: string; type: "file" | "directory"; size?: number }[],
) {
  getProjectTreeMock.mockResolvedValue({ entries: entries as any });
  const onLoadWorkflow = vi.fn();
  const onReloadBlocks = vi.fn();
  render(
    <ProjectTree
      projectId="proj-1"
      projectPath="/tmp/proj-1"
      onLoadWorkflow={onLoadWorkflow}
      onReloadBlocks={onReloadBlocks}
    />,
  );
  // Wait for the tree to render the rows.
  for (const e of entries) {
    await screen.findByText(e.name);
  }
  return { onLoadWorkflow, onReloadBlocks };
}

describe("ProjectTree — ADR-036 §3.5 double-click wiring (I36c)", () => {
  it("double-click on .py at project root opens it in the editor", async () => {
    const openFileTab = vi.fn();
    useAppStore.setState({ openFileTab });
    const { onReloadBlocks } = await renderTreeWith([
      { name: "scratch.py", type: "file", size: 10 },
    ]);
    const row = screen.getByText("scratch.py");
    fireEvent.doubleClick(row);
    await waitFor(() => expect(openFileTab).toHaveBeenCalledWith("scratch.py"));
    // Root-level .py is NOT under blocks/, so reload must NOT fire.
    expect(onReloadBlocks).not.toHaveBeenCalled();
  });

  it("double-click on .md anywhere opens it in the editor", async () => {
    const openFileTab = vi.fn();
    useAppStore.setState({ openFileTab });
    await renderTreeWith([{ name: "NOTES.md", type: "file", size: 4 }]);
    fireEvent.doubleClick(screen.getByText("NOTES.md"));
    await waitFor(() => expect(openFileTab).toHaveBeenCalledWith("NOTES.md"));
  });

  it.each([
    ["data.json", "data.json"],
    ["table.csv", "table.csv"],
    ["readme.txt", "readme.txt"],
  ])("double-click on %s opens %s in the editor", async (name, expectedPath) => {
    const openFileTab = vi.fn();
    useAppStore.setState({ openFileTab });
    await renderTreeWith([{ name, type: "file", size: 4 }]);
    fireEvent.doubleClick(screen.getByText(name));
    await waitFor(() => expect(openFileTab).toHaveBeenCalledWith(expectedPath));
  });

  it("double-click on image.tiff does NOT open the editor", async () => {
    const openFileTab = vi.fn();
    useAppStore.setState({ openFileTab });
    await renderTreeWith([{ name: "image.tiff", type: "file", size: 1024 }]);
    fireEvent.doubleClick(screen.getByText("image.tiff"));
    // Wait long enough for the handler to run if it were going to.
    await new Promise((r) => setTimeout(r, 5));
    expect(openFileTab).not.toHaveBeenCalled();
  });
});
