// #2141 — edge/port colour parity for dynamic-port blocks.
//
// A freshly dropped Load block never materializes ``core_type`` into
// ``config.params`` (the palette drop only seeds ``direction``). The port
// surface (BlockNode) fell back to the config-schema default ("DataFrame")
// while the edge surface (WorkflowCanvas.useFlowEdges) did not, so the port
// rendered DataFrame amber and the edge rendered the DataObject gray fallback.
// Both surfaces now resolve the driving value through the same
// ``resolveDrivingConfigValue`` helper; this file proves the parity end to end
// on the rendered canvas.

import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { resetAppStore } from "../../testUtils";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  DynamicPortsConfig,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import { WorkflowCanvas } from "../WorkflowCanvas";

const listTypes = vi.fn();
vi.mock("../../lib/api/code", () => ({
  codeApi: {
    listTypes: () => listTypes(),
  },
}));

/** React Flow measures its container; jsdom has no layout engine. The mocks
 * below follow the official React Flow jsdom testing recipe: a ResizeObserver
 * that fires immediately (so nodes register dimensions), a DOMMatrixReadOnly
 * that understands scale transforms, offset sizes, and an SVG getBBox. */
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

function port(name: string, direction: "input" | "output", accepted: string[]): BlockPortResponse {
  return {
    name,
    direction,
    accepted_types: accepted,
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

/** Mirrors the LoadData backend ``dynamic_ports`` ClassVar shape. */
const LOAD_DATA_DYNAMIC: DynamicPortsConfig = {
  source_config_key: "core_type",
  output_port_mapping: {
    data: {
      Array: ["Array"],
      DataFrame: ["DataFrame"],
      Series: ["Series"],
      Text: ["Text"],
      Artifact: ["Artifact"],
      CompositeData: ["CompositeData"],
    },
  },
};

function loadSchema(): BlockSchemaResponse {
  return {
    name: "Load Data",
    type_name: "load_data",
    base_category: "io",
    subcategory: "io",
    description: "",
    version: "1.0",
    input_ports: [],
    // Static placeholder port — the dynamic mapping retypes it per instance.
    output_ports: [port("data", "output", ["DataObject"])],
    config_schema: {
      type: "object",
      properties: {
        core_type: { type: "string", default: "DataFrame" },
      },
      required: ["core_type"],
    },
    type_hierarchy: [
      { name: "DataObject", base_type: "", description: "" },
      { name: "DataFrame", base_type: "DataObject", description: "" },
      { name: "Array", base_type: "DataObject", description: "" },
    ],
    dynamic_ports: LOAD_DATA_DYNAMIC,
    direction: "input",
  };
}

function sinkSchema(): BlockSchemaResponse {
  return {
    name: "Sink",
    type_name: "sink_block",
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [port("input", "input", ["DataFrame", "Array"])],
    output_ports: [],
    config_schema: { type: "object", properties: {} },
    type_hierarchy: [
      { name: "DataObject", base_type: "", description: "" },
      { name: "DataFrame", base_type: "DataObject", description: "" },
      { name: "Array", base_type: "DataObject", description: "" },
    ],
    dynamic_ports: null,
    direction: null,
  };
}

function loadNode(params: Record<string, unknown>): WorkflowNode {
  // The palette drop seeds only ``direction`` — ``core_type`` is absent until
  // the user touches the dropdown (useCanvasHandlers.handleAddBlockFromPalette).
  return { id: "load1", block_type: "load_data", config: { params } };
}

const SINK_NODE: WorkflowNode = { id: "sink1", block_type: "sink_block", config: { params: {} } };
const EDGE: WorkflowEdge = { source: "load1:data", target: "sink1:input" };

function renderCanvas(nodes: WorkflowNode[]) {
  return render(
    <ReactFlowProvider>
      <WorkflowCanvas
        blockErrorSummaries={{}}
        blockErrors={{}}
        blockStates={{}}
        blocks={[]}
        edges={[EDGE]}
        minimapVisible={false}
        nodes={nodes}
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
        schemas={{ load_data: loadSchema(), sink_block: sinkSchema() }}
        selectedNodeId={null}
      />
    </ReactFlowProvider>,
  );
}

function edgePath(container: HTMLElement): SVGElement {
  const path = container.querySelector(".react-flow__edge-path");
  // jsdom exposes SVGElement but not the SVGPathElement subclass.
  if (!(path instanceof SVGElement)) {
    throw new Error("no .react-flow__edge-path rendered");
  }
  return path;
}

function handleFor(container: HTMLElement, portName: string): HTMLElement {
  const handle = container.querySelector(`[data-handleid="${portName}"]`);
  if (!(handle instanceof HTMLElement)) {
    throw new Error(`no handle for ${portName}`);
  }
  return handle;
}

beforeEach(() => {
  resetAppStore();
  installReactFlowJsdomMocks();
  listTypes.mockResolvedValue({ types: [] });
});

afterEach(() => {
  cleanup();
  listTypes.mockReset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("edge/port colour parity for dynamic-port blocks (#2141)", () => {
  it("colours the edge by the schema-default core_type when the param was never set", () => {
    // Regression: the edge used to fall back to the DataObject gray (#374151)
    // here while the port rendered the DataFrame amber.
    const { container } = renderCanvas([loadNode({}), SINK_NODE]);

    const dataFrameRgb = "rgb(245, 158, 11)"; // typeColorMap.DataFrame #f59e0b
    expect(handleFor(container, "data").style.backgroundColor).toBe(dataFrameRgb);
    // jsdom normalizes backgroundColor to rgb() but keeps stroke as authored.
    expect(edgePath(container).style.stroke).toBe("#f59e0b");
  });

  it("colours the edge by the configured core_type when the param is set", () => {
    const { container } = renderCanvas([loadNode({ core_type: "Array" }), SINK_NODE]);

    const arrayRgb = "rgb(59, 130, 246)"; // typeColorMap.Array #3b82f6
    expect(handleFor(container, "data").style.backgroundColor).toBe(arrayRgb);
    expect(edgePath(container).style.stroke).toBe("#3b82f6");
  });
});
