/**
 * ADR-054 spec 4 (T-003) — the canvas node context menu and the packaged-node
 * double-click (FR-002, FR-003, FR-004).
 *
 * Split in two, because the two halves are two different kinds of fact. What
 * the menu may offer is decided in `useCanvasHandlers` from the run's outputs,
 * and is tested by calling the handler; what the menu draws when it is told
 * that is tested by rendering `NodeContextMenu`. Rendering the whole canvas to
 * assert either would mean standing up React Flow for a `<div>` positioned at
 * the pointer.
 */

import type { Node } from "@xyflow/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BlockSummary, WorkflowNode } from "../../../types/api";
import { NodeContextMenu, type CanvasContextMenuState } from "../NodeContextMenu";
import { useCanvasHandlers } from "../useCanvasHandlers";

afterEach(cleanup);

const REACT_FLOW = {
  getNode: () => undefined,
  screenToFlowPosition: (p: { x: number; y: number }) => p,
} as unknown as Parameters<typeof useCanvasHandlers>[0]["reactFlow"];

function baseOpts(overrides: Record<string, unknown> = {}) {
  return {
    reactFlow: REACT_FLOW,
    edges: [],
    onAddNode: vi.fn(),
    onConnect: vi.fn(async () => {}),
    onDeleteEdge: vi.fn(),
    onDeleteNode: vi.fn(),
    onSelectNode: vi.fn(),
    onUpdateNodePosition: vi.fn(),
    setDragPositions: vi.fn(),
    setDragSizes: vi.fn(),
    ...overrides,
  } as unknown as Parameters<typeof useCanvasHandlers>[0];
}

function flowNode(id: string, label = "Load Data"): Node {
  return { id, position: { x: 0, y: 0 }, data: { label } } as unknown as Node;
}

function mouseEvent(): React.MouseEvent {
  return {
    clientX: 120,
    clientY: 80,
    preventDefault: vi.fn(),
  } as unknown as React.MouseEvent;
}

describe("what the menu may offer (FR-002)", () => {
  const nodes: WorkflowNode[] = [
    { id: "n1", block_type: "load_data", config: {} },
    { id: "n2", block_type: "load_data", config: {} },
  ];

  it("offers the explore action for a node whose outputs the runtime reports", () => {
    const onOpenNodeContextMenu = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(
        baseOpts({
          nodes,
          blockOutputs: { n1: { table: { ref: "abc" } } },
          onOpenNodeContextMenu,
        }),
      ),
    );
    result.current.handleNodeContextMenu(mouseEvent(), flowNode("n1"));
    expect(onOpenNodeContextMenu).toHaveBeenCalledTimes(1);
    const menu = onOpenNodeContextMenu.mock.calls[0][0] as CanvasContextMenuState;
    expect(menu.canExplore).toBe(true);
    expect(menu.disabledReason).toBeNull();
    expect(menu.nodeId).toBe("n1");
    expect(menu.x).toBe(120);
  });

  it("disables it with a reason for a node that has produced nothing", () => {
    const onOpenNodeContextMenu = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(baseOpts({ nodes, blockOutputs: {}, onOpenNodeContextMenu })),
    );
    result.current.handleNodeContextMenu(mouseEvent(), flowNode("n2"));
    const menu = onOpenNodeContextMenu.mock.calls[0][0] as CanvasContextMenuState;
    expect(menu.canExplore).toBe(false);
    expect(menu.disabledReason).toBe("This block has not produced any outputs yet.");
  });

  it("treats an empty output payload as nothing to explore", () => {
    const onOpenNodeContextMenu = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(baseOpts({ nodes, blockOutputs: { n1: {} }, onOpenNodeContextMenu })),
    );
    result.current.handleNodeContextMenu(mouseEvent(), flowNode("n1"));
    expect((onOpenNodeContextMenu.mock.calls[0][0] as CanvasContextMenuState).canExplore).toBe(
      false,
    );
  });

  it("suppresses the browser menu only when there is a menu to open", () => {
    const withHandler = renderHook(() =>
      useCanvasHandlers(baseOpts({ nodes, onOpenNodeContextMenu: vi.fn() })),
    );
    const event = mouseEvent();
    withHandler.result.current.handleNodeContextMenu(event, flowNode("n1"));
    expect(event.preventDefault).toHaveBeenCalled();

    const without = renderHook(() => useCanvasHandlers(baseOpts({ nodes })));
    const second = mouseEvent();
    without.result.current.handleNodeContextMenu(second, flowNode("n1"));
    expect(second.preventDefault).not.toHaveBeenCalled();
  });
});

describe("what the menu draws (FR-003)", () => {
  const enabled: CanvasContextMenuState = {
    x: 10,
    y: 20,
    nodeId: "n1",
    nodeLabel: "Load Data",
    canExplore: true,
    disabledReason: null,
  };

  it("carries the explore action alone", () => {
    render(<NodeContextMenu menu={enabled} onClose={vi.fn()} onExplore={vi.fn()} />);
    const menu = screen.getByTestId("canvas-node-context-menu");
    expect(menu.querySelectorAll("button")).toHaveLength(1);
    expect(screen.getByTestId("canvas-explore-outputs").textContent).toBe("Explore outputs");
  });

  it("opens the tab and closes itself when the action is taken", () => {
    const onExplore = vi.fn();
    const onClose = vi.fn();
    render(<NodeContextMenu menu={enabled} onClose={onClose} onExplore={onExplore} />);
    fireEvent.click(screen.getByTestId("canvas-explore-outputs"));
    expect(onExplore).toHaveBeenCalledWith("n1");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows the reason and refuses the click when there is nothing to explore", () => {
    const onExplore = vi.fn();
    render(
      <NodeContextMenu
        menu={{
          ...enabled,
          canExplore: false,
          disabledReason: "This block has not produced any outputs yet.",
        }}
        onClose={vi.fn()}
        onExplore={onExplore}
      />,
    );
    const action = screen.getByTestId("canvas-explore-outputs") as HTMLButtonElement;
    expect(action.disabled).toBe(true);
    expect(screen.getByTestId("canvas-explore-disabled-reason").textContent).toBe(
      "This block has not produced any outputs yet.",
    );
    fireEvent.click(action);
    expect(onExplore).not.toHaveBeenCalled();
  });

  it("renders nothing when no node was right-clicked", () => {
    const { container } = render(
      <NodeContextMenu menu={null} onClose={vi.fn()} onExplore={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });
});

describe("the packaged-node double-click (FR-004)", () => {
  const packaged: BlockSummary = {
    name: "MyBlock",
    type_name: "my_block",
    base_category: "code",
    subcategory: "",
    description: "",
    version: "1",
    input_ports: [],
    output_ports: [],
    notebook_filename: "my_block.ipynb",
  };
  const plain: BlockSummary = { ...packaged, type_name: "load_data", notebook_filename: null };
  const nodes: WorkflowNode[] = [
    { id: "n1", block_type: "my_block", config: {} },
    { id: "n2", block_type: "load_data", config: {} },
    {
      id: "n3",
      block_type: "subworkflow_block",
      config: { ref: { path: "subworkflows/inner.yaml" } },
    },
  ];

  it("opens the packaged block's notebook, bound to the node", () => {
    const onOpenPackagedNotebook = vi.fn();
    const onOpenSubworkflow = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(
        baseOpts({
          nodes,
          blocks: [packaged, plain],
          onOpenPackagedNotebook,
          onOpenSubworkflow,
        }),
      ),
    );
    result.current.handleNodeDoubleClick({}, flowNode("n1"));
    expect(onOpenPackagedNotebook).toHaveBeenCalledWith("my_block", "n1");
    expect(onOpenSubworkflow).not.toHaveBeenCalled();
  });

  it("leaves an ordinary block's double-click a no-op, as it was", () => {
    const onOpenPackagedNotebook = vi.fn();
    const onOpenSubworkflow = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(
        baseOpts({ nodes, blocks: [packaged, plain], onOpenPackagedNotebook, onOpenSubworkflow }),
      ),
    );
    result.current.handleNodeDoubleClick({}, flowNode("n2"));
    expect(onOpenPackagedNotebook).not.toHaveBeenCalled();
    expect(onOpenSubworkflow).not.toHaveBeenCalled();
  });

  it("still opens a subworkflow, which is the node it already recognised", () => {
    const onOpenPackagedNotebook = vi.fn();
    const onOpenSubworkflow = vi.fn();
    const { result } = renderHook(() =>
      useCanvasHandlers(
        baseOpts({ nodes, blocks: [packaged, plain], onOpenPackagedNotebook, onOpenSubworkflow }),
      ),
    );
    result.current.handleNodeDoubleClick({}, flowNode("n3"));
    expect(onOpenSubworkflow).toHaveBeenCalledWith("subworkflows/inner.yaml", "n3__");
    expect(onOpenPackagedNotebook).not.toHaveBeenCalled();
  });

  it("treats no block as packaged while the backend sends no marker", () => {
    // F-A1-001 in the follow-up register: `BlockSummary` carries no
    // packaged-notebook marker on the wire yet, so the predicate answers
    // `false` for every real block and the double-click keeps its old
    // behaviour rather than sending a speculative open.
    const onOpenPackagedNotebook = vi.fn();
    const asBackendSendsIt: BlockSummary = { ...packaged };
    delete (asBackendSendsIt as { notebook_filename?: unknown }).notebook_filename;
    const { result } = renderHook(() =>
      useCanvasHandlers(baseOpts({ nodes, blocks: [asBackendSendsIt], onOpenPackagedNotebook })),
    );
    result.current.handleNodeDoubleClick({}, flowNode("n1"));
    expect(onOpenPackagedNotebook).not.toHaveBeenCalled();
  });
});
