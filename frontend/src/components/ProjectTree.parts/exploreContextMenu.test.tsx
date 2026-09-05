/**
 * ADR-054 spec 4 (T-003) — the data tree's explore action (FR-002, FR-003).
 *
 * The tree already has a context menu, so this is one item added to it rather
 * than a menu built. Two things are worth pinning: the item is offered for a
 * *file* in the *data* tree and nowhere else, and taking it opens a session
 * over that file's path rather than a preview.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";
import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../../store";
import { ProjectTree } from "../ProjectTree";
import { ContextMenu } from "./ContextMenu";
import type { ContextMenuState, TreeNodeData } from "./types";

const openExploreSession = vi.fn();
vi.mock("../../lib/api/explore", () => ({
  exploreApi: {
    openExploreSession: (...args: unknown[]) => openExploreSession(...args),
  },
}));

const getProjectTree = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectTree: (...args: unknown[]) => getProjectTree(...args),
      revealInExplorer: vi.fn(),
    },
  };
});

function fileNode(name = "measurements.csv", path = "data/raw/measurements.csv"): TreeNodeData {
  return { name, path, type: "file", loaded: true, expanded: false } as TreeNodeData;
}

function dirNode(): TreeNodeData {
  return {
    name: "raw",
    path: "data/raw",
    type: "directory",
    loaded: true,
    expanded: true,
  } as TreeNodeData;
}

function menuFor(node: TreeNodeData): ContextMenuState {
  return { x: 40, y: 60, node };
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  openExploreSession.mockReset();
  getProjectTree.mockReset();
  getProjectTree.mockResolvedValue({
    entries: [{ name: "measurements.csv", type: "file", size: 12 }],
  });
  openExploreSession.mockResolvedValue({
    session_id: "sess-tree",
    notebook_path: "explore/measurements.ipynb",
    has_kernel: false,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [],
  });
});

afterEach(cleanup);

const HANDLERS = {
  onClose: vi.fn(),
  onCopyName: vi.fn(),
  onCopyPath: vi.fn(),
  onReveal: vi.fn(),
};

describe("the menu item (FR-003)", () => {
  it("offers the explore action for a file when a handler is supplied", () => {
    render(<ContextMenu contextMenu={menuFor(fileNode())} {...HANDLERS} onExplore={vi.fn()} />);
    expect(screen.getByTestId("tree-explore-file").textContent).toBe("Explore in notebook");
  });

  it("does not offer it for a directory", () => {
    render(<ContextMenu contextMenu={menuFor(dirNode())} {...HANDLERS} onExplore={vi.fn()} />);
    expect(screen.queryByTestId("tree-explore-file")).toBeNull();
  });

  it("does not offer it when no handler is supplied, and leaves the rest alone", () => {
    render(<ContextMenu contextMenu={menuFor(fileNode())} {...HANDLERS} />);
    expect(screen.queryByTestId("tree-explore-file")).toBeNull();
    // The three actions the menu already had are untouched.
    expect(screen.getByText("Copy Name")).toBeTruthy();
    expect(screen.getByText("Copy Path")).toBeTruthy();
    expect(screen.getByText("Reveal in Explorer")).toBeTruthy();
  });

  it("calls the handler with the node and closes", () => {
    const onExplore = vi.fn();
    const onClose = vi.fn();
    render(
      <ContextMenu
        contextMenu={menuFor(fileNode())}
        {...HANDLERS}
        onClose={onClose}
        onExplore={onExplore}
      />,
    );
    fireEvent.click(screen.getByTestId("tree-explore-file"));
    expect(onExplore).toHaveBeenCalledWith(fileNode());
    expect(onClose).toHaveBeenCalled();
  });
});

describe("which tree offers it (FR-002)", () => {
  const treeProps = {
    projectId: "proj-1",
    projectPath: "/tmp/proj",
    onLoadWorkflow: vi.fn(),
    onReloadBlocks: vi.fn(),
  };

  async function rightClickFirstFile() {
    const row = await screen.findByText("measurements.csv");
    fireEvent.contextMenu(row);
  }

  it("is offered in the Data section", async () => {
    render(<ProjectTree {...treeProps} rootPath="data" title="Data" />);
    await rightClickFirstFile();
    expect(screen.getByTestId("tree-explore-file")).toBeTruthy();
  });

  it("is not offered in the Project tree", async () => {
    // FR-002 names the *data* tree. The Project tree lists source, config and
    // workflow files, and "explore this file in a notebook" is not an offer
    // that means anything over a block's `.py`.
    render(<ProjectTree {...treeProps} />);
    await rightClickFirstFile();
    expect(screen.queryByTestId("tree-explore-file")).toBeNull();
  });

  it("opens a session over the file it was taken on", async () => {
    render(<ProjectTree {...treeProps} rootPath="data" title="Data" />);
    await rightClickFirstFile();
    fireEvent.click(screen.getByTestId("tree-explore-file"));
    // The path stays project-relative even though the pane is rooted at
    // `data/`, which is what the session route takes.
    expect(openExploreSession).toHaveBeenCalledWith({
      source: "file",
      path: "data/measurements.csv",
    });
  });
});

describe("taking the action opens a session over the file (FR-002)", () => {
  it("sends the file source with the node's project-relative path", async () => {
    // The store action is what the tree calls; asserting it here rather than
    // through the whole tree keeps the fact — "a file opens a `file` session
    // over its own path" — separate from how the tree fetches its rows.
    await useAppStore.getState().openExploreTab({ source: "file", path: "data/raw/m.csv" });
    expect(openExploreSession).toHaveBeenCalledWith({
      source: "file",
      path: "data/raw/m.csv",
    });
  });

  it("puts the session in a tab keyed by the notebook path the backend chose", async () => {
    await useAppStore.getState().openExploreTab({ source: "file", path: "data/raw/m.csv" });
    const tabs = useAppStore.getState().tabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0].id).toBe("explore:explore/measurements.ipynb");
    expect(useAppStore.getState().activeTabId).toBe("explore:explore/measurements.ipynb");
  });

  it("activates the existing tab when the same notebook is opened twice (FR-001)", async () => {
    await useAppStore.getState().openExploreTab({ source: "file", path: "data/raw/m.csv" });
    await useAppStore.getState().openExploreTab({ source: "file", path: "data/raw/m.csv" });
    expect(useAppStore.getState().tabs).toHaveLength(1);
  });

  it("writes nothing and opens no tab when the backend refuses", async () => {
    openExploreSession.mockRejectedValueOnce(new Error("nothing to explore"));
    await expect(
      useAppStore.getState().openExploreTab({ source: "file", path: "data/raw/m.csv" }),
    ).rejects.toThrow("nothing to explore");
    expect(useAppStore.getState().tabs).toHaveLength(0);
    expect(Object.keys(useAppStore.getState().sessions)).toHaveLength(0);
  });
});
