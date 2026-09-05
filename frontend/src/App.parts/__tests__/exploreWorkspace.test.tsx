/**
 * ADR-054 spec 4 (T-002) — the workspace while an Explore tab is active
 * (FR-005, FR-006).
 *
 * One branch in the centre switch and one condition on the right column is the
 * whole of the layout change, and the thing worth asserting is as much what
 * does *not* move as what does: ADR-054 §4.4 chose a tab over a separate
 * application so the palette, the project tree and the block cards stay
 * available while a person explores, and that promise is kept by the left pane
 * and the bottom panel being untouched.
 *
 * Every heavy child is stubbed to a marker. The subject here is which regions
 * the workspace mounts for which active tab; what a canvas or a preview draws
 * inside its own box is its own test's business, and rendering React Flow,
 * Monaco and xterm to find out would make this suite slow and flaky for no
 * added assurance.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../../store";
import type { ExploreTab } from "../../store/types";
import type { ProjectResponse } from "../../types/api";

import { ProjectWorkspace, type ProjectWorkspaceProps } from "../ProjectWorkspace";

vi.mock("../../components/ActivityBar", () => ({
  ActivityBar: () => <div data-testid="stub-activity-bar" />,
}));
vi.mock("../../components/BlockPalette", () => ({
  BlockPalette: () => <div data-testid="stub-block-palette" />,
}));
vi.mock("../../components/BottomPanel", () => ({
  BottomPanel: () => <div data-testid="stub-bottom-panel" />,
}));
vi.mock("../../components/CodeEditor", () => ({
  CodeEditor: () => <div data-testid="stub-code-editor" />,
}));
vi.mock("../../components/DataPreview", () => ({
  DataPreview: () => <div data-testid="stub-data-preview" />,
}));
vi.mock("../../components/DataPreview.parts/PreviewHost", () => ({
  PreviewHost: () => <div data-testid="stub-preview-host" />,
}));
vi.mock("../../components/palette/tips/PaletteTipCard", () => ({
  PaletteTipCard: () => <div data-testid="stub-tip-card" />,
}));
vi.mock("../../components/PanelPalette", () => ({
  PanelPalette: () => <div data-testid="stub-panel-palette" />,
}));
vi.mock("../../components/ProjectTree", () => ({
  ProjectTree: () => <div data-testid="stub-project-tree" />,
}));
vi.mock("../../components/promotion/revealInLibrary", () => ({
  useLibraryReveal: () => null,
}));
vi.mock("../../components/TabBar", () => ({
  TabBar: () => <div data-testid="stub-tab-bar" />,
}));
vi.mock("../../components/TypePalette", () => ({
  TypePalette: () => <div data-testid="stub-type-palette" />,
}));
vi.mock("../../components/WorkflowPanel", () => ({
  WorkflowPanel: () => <div data-testid="stub-workflow-panel" />,
}));
vi.mock("../../components/WorkflowCanvas", () => ({
  WorkflowCanvas: () => <div data-testid="stub-workflow-canvas" />,
}));
vi.mock("../../components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-workspace";

const project: ProjectResponse = {
  id: "proj-1",
  name: "Project",
  path: "/tmp/proj",
} as ProjectResponse;

function exploreTab(): ExploreTab {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: SESSION_ID,
    displayName: "analysis.ipynb",
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
  };
}

function props(overrides: Partial<ProjectWorkspaceProps> = {}): ProjectWorkspaceProps {
  const noop = () => {};
  return {
    currentProject: project,
    workflowId: "wf-1",
    leftTab: "blocks",
    onLeftTabChange: noop,
    onActivitySelect: noop,
    paletteCollapsed: false,
    blocks: [],
    paletteSearch: "",
    setPaletteSearch: noop,
    onAddBlockFromPalette: noop,
    onReloadBlocks: noop,
    onLoadWorkflowById: noop,
    tabs: [],
    activeTabId: null,
    activeFileTab: null,
    activePreviewTab: null,
    switchTab: noop,
    closeTab: noop,
    onNewWorkflowTab: noop,
    updateFileTabContent: noop,
    saveFileTab: async () => {},
    blockStates: {},
    blockOutputs: {},
    blockErrors: {},
    blockErrorSummaries: {},
    blockSchemas: {},
    workflowNodes: [],
    workflowEdges: [],
    selectedNodeId: null,
    minimapVisible: true,
    onCanvasAddNode: noop,
    onCanvasConnect: async () => {},
    onCanvasDeleteEdge: noop,
    onCanvasDeleteNode: noop,
    onErrorClick: noop,
    onCanvasPaneClick: noop,
    onRunBlock: noop,
    onSelectNode: noop,
    onUpdateNodeConfig: noop,
    onUpdateNodePosition: noop,
    onResizeNode: noop,
    onOpenSubworkflow: noop,
    onLocateSubworkflow: noop,
    readability: {
      focusMode: { enabled: false, selectedIds: [], depth: 1 },
      onWarningClick: noop,
      onEnterFocusMode: noop,
      onExitFocusMode: noop,
      onTidyLayout: noop,
    },
    bottomPanelRef: { current: null },
    bottomPanelPinned: false,
    toggleBottomPanelPinned: noop,
    activeBottomTab: "config",
    onBottomTabChange: noop,
    logEntries: [],
    unreadLogsCount: 0,
    selectedNode: null,
    selectedSchema: undefined,
    selectedNodeLabel: "",
    setPanelSize: noop,
    ...overrides,
  };
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {} });
  useAppStore.getState().applyExploreSession({
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: false,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [{ cell_id: "c1", cell_type: "code", source: "x = 1", enabled: true, marks: [] }],
  });
});

afterEach(cleanup);

describe("the right column swaps while an Explore tab is active (FR-005)", () => {
  it("renders the notebook pane in place of the data preview", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: tab.id })} />);
    expect(screen.getByTestId("explore-notebook-pane")).toBeTruthy();
    expect(screen.queryByTestId("stub-data-preview")).toBeNull();
  });

  it("restores the data preview when the active tab is not an Explore tab", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: "tab-workflow-1" })} />);
    expect(screen.getByTestId("stub-data-preview")).toBeTruthy();
    expect(screen.queryByTestId("explore-notebook-pane")).toBeNull();
  });

  it("renders the preview when there is no Explore tab at all", () => {
    render(<ProjectWorkspace {...props()} />);
    expect(screen.getByTestId("stub-data-preview")).toBeTruthy();
  });
});

describe("the centre switch gains one branch (FR-005)", () => {
  it("renders the Explore tab's centre in place of the canvas", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: tab.id })} />);
    expect(screen.getByTestId("explore-tab")).toBeTruthy();
    expect(screen.getByTestId("explore-session-toolbar")).toBeTruthy();
    expect(screen.getByTestId("explore-variable-strip-region")).toBeTruthy();
    expect(screen.queryByTestId("stub-workflow-canvas")).toBeNull();
  });

  it("renders the canvas again when the Explore tab is not the active one", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: "tab-workflow-1" })} />);
    expect(screen.getByTestId("stub-workflow-canvas")).toBeTruthy();
    expect(screen.queryByTestId("explore-tab")).toBeNull();
  });
});

describe("the left pane and the bottom panel do not change (ADR-054 §4.4)", () => {
  it("keeps the palette and the bottom panel while an Explore tab is active", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: tab.id })} />);
    expect(screen.getByTestId("stub-block-palette")).toBeTruthy();
    expect(screen.getByTestId("stub-bottom-panel")).toBeTruthy();
    expect(screen.getByTestId("stub-activity-bar")).toBeTruthy();
    expect(screen.getByTestId("stub-tab-bar")).toBeTruthy();
  });

  it("keeps the project tree section too, so a file is still one right-click away", () => {
    const tab = exploreTab();
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: tab.id, leftTab: "data" })} />);
    expect(screen.getByTestId("stub-project-tree")).toBeTruthy();
  });

  it("renders the same left pane and bottom panel with no Explore tab, so nothing moved", () => {
    render(<ProjectWorkspace {...props()} />);
    expect(screen.getByTestId("stub-block-palette")).toBeTruthy();
    expect(screen.getByTestId("stub-bottom-panel")).toBeTruthy();
  });
});

describe("a collapsed notebook leaves the centre usable (FR-006)", () => {
  it("keeps the toolbar and the panel host when the notebook pane renders nothing", () => {
    const tab = { ...exploreTab(), notebookVisible: false };
    render(<ProjectWorkspace {...props({ tabs: [tab], activeTabId: tab.id })} />);
    expect(screen.queryByTestId("explore-notebook-pane")).toBeNull();
    expect(screen.getByTestId("explore-session-toolbar")).toBeTruthy();
    expect(screen.getByTestId("explore-panel-host")).toBeTruthy();
  });
});
