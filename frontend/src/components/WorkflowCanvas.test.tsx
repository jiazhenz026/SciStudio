/**
 * ADR-054 Phase D (#2354) — the canvas block context menu (FR-035), and the
 * half of FR-034 and FR-023 that is decided on the canvas.
 *
 * These are US6 acceptance scenarios 1 and 2 and US1 acceptance 1, on the real
 * rendered canvas rather than against the helpers: the scenarios are about what
 * a user sees when they right-click a block, and a test of `portsForMiniApp`
 * alone would still pass if the menu never rendered it.
 *
 * The jsdom mocks are the official React Flow recipe, copied from
 * `edgePortColorParity.test.tsx` — jsdom has no layout engine, and without them
 * React Flow measures nothing and renders no nodes to right-click.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import type { MiniAppSummary, MiniAppTarget } from "../miniapps/types";
import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import type { BlockPortResponse, BlockSchemaResponse, WorkflowNode } from "../types/api";

import { WorkflowCanvas } from "./WorkflowCanvas";

class MockResizeObserver {
  callback: globalThis.ResizeObserverCallback;
  constructor(callback: globalThis.ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    this.callback([{ target } as globalThis.ResizeObserverEntry], this);
  }
  unobserve() {}
  disconnect() {}
}

class MockDOMMatrixReadOnly {
  m22: number;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([\d.]+)\)/)?.[1];
    this.m22 = scale !== undefined ? Number(scale) : 1;
  }
}

function installReactFlowJsdomMocks() {
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  vi.stubGlobal("DOMMatrixReadOnly", MockDOMMatrixReadOnly);
  Object.defineProperties(globalThis.HTMLElement.prototype, {
    offsetHeight: {
      configurable: true,
      get(this: HTMLElement) {
        return parseFloat(this.style.height) || 1;
      },
    },
    offsetWidth: {
      configurable: true,
      get(this: HTMLElement) {
        return parseFloat(this.style.width) || 1;
      },
    },
  });
  (globalThis.SVGElement.prototype as { getBBox?: () => unknown }).getBBox = () => ({
    x: 0,
    y: 0,
    width: 0,
    height: 0,
  });
}

const HIERARCHY = [
  { name: "DataObject", base_type: "", description: "" },
  { name: "Image", base_type: "DataObject", description: "" },
  { name: "Mask", base_type: "Image", description: "" },
  { name: "DataFrame", base_type: "DataObject", description: "" },
];

function port(name: string, accepted: string[]): BlockPortResponse {
  return {
    name,
    direction: "output",
    accepted_types: accepted,
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

function schema(name: string, outputs: BlockPortResponse[]): BlockSchemaResponse {
  return {
    name,
    type_name: name,
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [],
    output_ports: outputs,
    config_schema: { type: "object", properties: {} },
    type_hierarchy: HIERARCHY,
    dynamic_ports: null,
    direction: null,
  };
}

const SCHEMAS: Record<string, BlockSchemaResponse> = {
  segment: schema("segment", [port("mask", ["Mask"])]),
  two_images: schema("two_images", [port("left", ["Image"]), port("right", ["Image"])]),
  tabulate: schema("tabulate", [port("table", ["DataFrame"])]),
};

const NODES: WorkflowNode[] = [
  { id: "segment1", block_type: "segment", config: { params: {} } },
  { id: "pair1", block_type: "two_images", config: { params: {} } },
  { id: "table1", block_type: "tabulate", config: { params: {} } },
  { id: "fresh1", block_type: "segment", config: { params: {} } },
];

/** What the latest run produced. `fresh1` has never run. */
const OUTPUTS: Record<string, Record<string, unknown>> = {
  segment1: { mask: { data_ref: "ref-mask" } },
  pair1: { left: { data_ref: "ref-left" }, right: { data_ref: "ref-right" } },
  table1: { table: { data_ref: "ref-table" } },
};

function miniApp(overrides: Partial<MiniAppSummary> & { panel_id: string }): MiniAppSummary {
  return {
    name: overrides.panel_id,
    description: "",
    type: "Image",
    tier: "project",
    directory: `/p/panels/${overrides.panel_id}`,
    has_python: true,
    ...overrides,
  };
}

const THRESHOLD = miniApp({ panel_id: "threshold", name: "Threshold explorer", type: "Image" });
const TABLE_APP = miniApp({ panel_id: "tabler", name: "Table browser", type: "DataFrame" });

interface Handlers {
  onOpenMiniApp: Mock<(summary: MiniAppSummary, target: MiniAppTarget) => void>;
  onNewMiniApp: Mock<(target: MiniAppTarget | null) => void>;
}

function renderCanvas(miniApps: MiniAppSummary[] = [THRESHOLD, TABLE_APP]): {
  container: HTMLElement;
  handlers: Handlers;
} {
  const handlers: Handlers = { onOpenMiniApp: vi.fn(), onNewMiniApp: vi.fn() };
  const { container } = render(
    <ReactFlowProvider>
      <WorkflowCanvas
        blockErrorSummaries={{}}
        blockErrors={{}}
        blockOutputs={OUTPUTS}
        blockStates={{}}
        blocks={Object.values(SCHEMAS).map((item) => ({
          ...item,
          subcategory: "",
          version: "1.0",
        }))}
        edges={[]}
        miniApps={miniApps}
        minimapVisible={false}
        nodes={NODES}
        onAddNode={vi.fn()}
        onConnect={vi.fn(async () => {})}
        onDeleteEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onErrorClick={vi.fn()}
        onNewMiniApp={handlers.onNewMiniApp}
        onOpenMiniApp={handlers.onOpenMiniApp}
        onResizeNode={vi.fn()}
        onRunBlock={vi.fn()}
        onSelectNode={vi.fn()}
        onUpdateNodeConfig={vi.fn()}
        onUpdateNodePosition={vi.fn()}
        schemas={SCHEMAS}
        selectedNodeId={null}
      />
    </ReactFlowProvider>,
  );
  return { container, handlers };
}

function rightClick(container: HTMLElement, nodeId: string): void {
  const node = container.querySelector(`.react-flow__node[data-id="${nodeId}"]`);
  if (!(node instanceof HTMLElement)) throw new Error(`no rendered node ${nodeId}`);
  fireEvent.contextMenu(node);
}

async function hoverDetails(container: HTMLElement, nodeId: string): Promise<void> {
  const node = container.querySelector(
    `.react-flow__node[data-id="${nodeId}"] [data-testid="block-node-shell"]`,
  );
  if (!(node instanceof HTMLElement)) throw new Error(`no rendered node ${nodeId}`);
  fireEvent.mouseEnter(node);
  await waitFor(() => expect(screen.getByTestId("block-detail-popover")).toBeInTheDocument());
}

beforeEach(() => {
  resetAppStore();
  installReactFlowJsdomMocks();
  // The canvas reads the open workflow's id for the MiniApp target, and the
  // type catalogue is pre-seeded so nothing reaches for the network.
  useAppStore.setState({ workflowId: "main", types: [], typesLoaded: true });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("canvas block hover actions (ADR-054 FR-035)", async () => {
  it("offers the MiniApps whose declared type matches an output, and New MiniApp", async () => {
    // US6 acceptance 1, canvas half: `mask` is a `Mask`, which is a subtype of
    // the `Image` the threshold explorer declares.
    const { container } = renderCanvas();
    await hoverDetails(container, "segment1");

    expect(screen.getByTestId("canvas-block-detail-actions")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-detail-miniapp-threshold")).toHaveTextContent(
      "Open in Threshold explorer",
    );
    expect(screen.getByTestId("canvas-detail-new-miniapp")).toBeEnabled();
  });

  it("offers New MiniApp and no Image MiniApp on a DataFrame block", async () => {
    // US6 acceptance 2, verbatim: the menu must not offer a MiniApp that could
    // not read this block's output. `DataFrame` is not an `Image`, and the
    // subtype rule is directional — a bidirectional compatibility check would
    // have offered it here.
    const { container } = renderCanvas();
    await hoverDetails(container, "table1");

    expect(screen.getByTestId("canvas-detail-new-miniapp")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-detail-miniapp-threshold")).toBeNull();
    expect(screen.getByTestId("canvas-detail-miniapp-tabler")).toBeInTheDocument();
  });

  it("pre-fills the block's output when New MiniApp is chosen", async () => {
    // US1 acceptance 1: the dialog opens with THAT block's output.
    const { container, handlers } = renderCanvas();
    await hoverDetails(container, "segment1");
    fireEvent.click(screen.getByTestId("canvas-detail-new-miniapp"));

    expect(handlers.onNewMiniApp).toHaveBeenCalledWith({
      workflow_id: "main",
      block_id: "segment1",
      port: "mask",
    });
    // The menu closes behind the choice.
    expect(screen.queryByTestId("block-detail-popover")).toBeNull();
  });

  it("opens a MiniApp on the block's only matching port without asking", async () => {
    // FR-034 — "asking only when several ports match".
    const { container, handlers } = renderCanvas();
    await hoverDetails(container, "segment1");
    fireEvent.click(screen.getByTestId("canvas-detail-miniapp-threshold"));

    expect(handlers.onOpenMiniApp).toHaveBeenCalledWith(THRESHOLD, {
      workflow_id: "main",
      block_id: "segment1",
      port: "mask",
    });
    expect(screen.queryByTestId("miniapp-target-picker")).toBeNull();
  });

  it("asks which port when several of the block's outputs match", async () => {
    // The other half of FR-034: `pair1` produced two Images, so the MiniApp
    // cannot be opened without a choice.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ sources: [] }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    const { container, handlers } = renderCanvas();
    await hoverDetails(container, "pair1");
    fireEvent.click(screen.getByTestId("canvas-detail-miniapp-threshold"));

    await waitFor(() => expect(screen.getByTestId("miniapp-target-picker")).toBeInTheDocument());
    expect(handlers.onOpenMiniApp).not.toHaveBeenCalled();
  });

  it("disables the entries with the reason for a block that has not produced anything", async () => {
    // FR-035 — disabled WITH THE REASON, not hidden: the entry is how a user
    // finds out MiniApps exist, and the reason is what they can act on.
    const { container, handlers } = renderCanvas();
    await hoverDetails(container, "fresh1");

    const entry = screen.getByTestId("canvas-detail-new-miniapp");
    expect(entry).toBeDisabled();
    expect(screen.getByTestId("canvas-detail-reason")).toHaveTextContent(/run it/i);
    expect(screen.queryByTestId("canvas-detail-miniapp-threshold")).toBeNull();
    fireEvent.click(entry);
    expect(handlers.onNewMiniApp).not.toHaveBeenCalled();
  });

  it("never mounts the removed custom right-click menu, even with MiniApp handlers", () => {
    const { container } = renderCanvas();
    rightClick(container, "segment1");
    expect(screen.queryByTestId("canvas-block-context-menu")).toBeNull();
    expect(screen.queryByTestId("block-detail-popover")).toBeNull();
  });

  it("leaves the browser's own menu alone when the workspace wired no MiniApp handlers", () => {
    // Every other consumer of this canvas — the subworkflow child view, the
    // colour-parity suite — must be unaffected by FR-035.
    const handlers = { onOpenMiniApp: undefined, onNewMiniApp: undefined };
    const { container } = render(
      <ReactFlowProvider>
        <WorkflowCanvas
          blockErrorSummaries={{}}
          blockErrors={{}}
          blockOutputs={OUTPUTS}
          blockStates={{}}
          blocks={[]}
          edges={[]}
          minimapVisible={false}
          nodes={NODES}
          onAddNode={vi.fn()}
          onConnect={vi.fn(async () => {})}
          onDeleteEdge={vi.fn()}
          onDeleteNode={vi.fn()}
          onErrorClick={vi.fn()}
          onResizeNode={vi.fn()}
          onRunBlock={vi.fn()}
          onSelectNode={vi.fn()}
          onUpdateNodeConfig={vi.fn()}
          onUpdateNodePosition={vi.fn()}
          schemas={SCHEMAS}
          selectedNodeId={null}
          {...handlers}
        />
      </ReactFlowProvider>,
    );
    rightClick(container, "segment1");
    expect(screen.queryByTestId("canvas-block-context-menu")).toBeNull();
  });
});
