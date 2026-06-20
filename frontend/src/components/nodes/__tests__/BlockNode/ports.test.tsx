// ADR-050 (#1698) — port topology on the square node.
//
// Covers:
//   - ADR-028 Addendum 1 §D4: dynamic-port live-update (port accepted_types
//     follow the driving config value, read from data.config).
//   - ADR-029: variadic +/- controls present on the rails and obeying
//     min/max limits (SC-004).
//   - port type colours + hover titles preserved (ADR-050 §2.4 keeps data
//     type semantics on ports, not in the body).

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";

import {
  LOAD_DATA_CONFIG_SCHEMA,
  LOAD_DATA_DYNAMIC,
  SAVE_DATA_DYNAMIC,
  makePort,
  makeSchema,
  openNativeDialogMock,
  renderNode,
} from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — dynamic port live-update (ADR-028 Addendum 1 §D4)", () => {
  function renderLoadData(coreType: string) {
    return renderNode({
      category: "io",
      blockType: "load_data",
      config: { core_type: coreType },
      inputPorts: [],
      outputPorts: [makePort("data", "output", ["DataObject"])],
      schema: makeSchema({
        base_category: "io",
        type_name: "load_data",
        direction: "input",
        input_ports: [],
        output_ports: [makePort("data", "output", ["DataObject"])],
        dynamic_ports: LOAD_DATA_DYNAMIC,
        config_schema: LOAD_DATA_CONFIG_SCHEMA,
      }),
    });
  }

  it("renders the LoadData output port with accepted_types=['Array'] when core_type=Array", () => {
    const { container } = renderLoadData("Array");
    const handles = container.querySelectorAll('[data-handleid="data"]');
    expect(handles.length).toBeGreaterThan(0);
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("Array"))).toBe(true);
    expect(titles.some((t) => t.includes("DataObject"))).toBe(false);
  });

  it("renders the LoadData output port with accepted_types=['DataFrame'] when core_type=DataFrame", () => {
    const { container } = renderLoadData("DataFrame");
    const handles = container.querySelectorAll('[data-handleid="data"]');
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("DataFrame"))).toBe(true);
    expect(titles.some((t) => t.includes("DataObject"))).toBe(false);
  });

  it("uses the schema default dynamic type when core_type is unset", () => {
    const { container } = renderNode({
      category: "io",
      blockType: "load_data",
      config: {},
      outputPorts: [makePort("data", "output", ["DataObject"])],
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        output_ports: [makePort("data", "output", ["DataObject"])],
        dynamic_ports: LOAD_DATA_DYNAMIC,
        config_schema: LOAD_DATA_CONFIG_SCHEMA,
      }),
    });
    const handles = container.querySelectorAll('[data-handleid="data"]');
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("DataFrame"))).toBe(true);
    expect(titles.some((t) => t.includes("DataObject"))).toBe(false);
  });

  it("renders the SaveData input port with accepted_types=['Series'] when core_type=Series", () => {
    const { container } = renderNode({
      category: "io",
      blockType: "save_data",
      config: { core_type: "Series" },
      inputPorts: [makePort("data", "input", ["DataObject"])],
      outputPorts: [],
      schema: makeSchema({
        base_category: "io",
        type_name: "save_data",
        direction: "output",
        input_ports: [makePort("data", "input", ["DataObject"])],
        dynamic_ports: SAVE_DATA_DYNAMIC,
      }),
    });
    const handles = container.querySelectorAll('[data-handleid="data"]');
    expect(handles.length).toBeGreaterThan(0);
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("Series"))).toBe(true);
  });

  it("static (non-dynamic) blocks render their ClassVar ports unchanged", () => {
    const { container } = renderNode({
      category: "process",
      outputPorts: [makePort("result", "output", ["Image"])],
      schema: makeSchema({
        base_category: "process",
        output_ports: [makePort("result", "output", ["Image"])],
        dynamic_ports: null,
      }),
    });
    const handles = container.querySelectorAll('[data-handleid="result"]');
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("Image"))).toBe(true);
  });
});

describe("BlockNode — port type colour + hover title (ADR-050 §2.4)", () => {
  it("colours a typed port handle and embeds the type name in its title", () => {
    const { container } = renderNode({
      category: "process",
      inputPorts: [makePort("image", "input", ["Image"])],
      schema: makeSchema({ input_ports: [makePort("image", "input", ["Image"])] }),
    });
    const handle = container.querySelector('[data-handleid="image"]') as HTMLElement | null;
    expect(handle).not.toBeNull();
    expect(handle?.getAttribute("title") ?? "").toContain("Image");
    // A typed (non-Any) handle is solid-filled, not the dashed Any style.
    expect(handle?.style.borderStyle).toBe("solid");
  });

  it("renders an Any-typed port with the dashed neutral ring", () => {
    const { container } = renderNode({
      category: "process",
      inputPorts: [makePort("in", "input", [])],
      schema: makeSchema({ input_ports: [makePort("in", "input", [])] }),
    });
    const handle = container.querySelector('[data-handleid="in"]') as HTMLElement | null;
    expect(handle).not.toBeNull();
    expect(handle?.style.borderStyle).toBe("dashed");
  });
});

describe("BlockNode — ADR-029 variadic +/- controls (SC-004)", () => {
  function renderVariadic(overrides: Record<string, unknown> = {}) {
    return renderNode({
      category: "process",
      blockType: "data_router",
      config: {
        input_ports: [
          { name: "in_1", types: ["DataObject"] },
          { name: "in_2", types: ["DataObject"] },
        ],
      },
      inputPorts: [makePort("in_1", "input"), makePort("in_2", "input")],
      outputPorts: [],
      schema: makeSchema({
        variadic_inputs: true,
        min_input_ports: 1,
        max_input_ports: 4,
        input_ports: [],
        ...overrides,
      }),
    });
  }

  it("shows the + add-port control when below the max input count", () => {
    renderVariadic();
    expect(screen.getByTitle("Add input port")).toBeInTheDocument();
  });

  it("shows per-port remove (×) controls when above the min input count", () => {
    renderVariadic();
    expect(screen.getByTitle('Remove port "in_1"')).toBeInTheDocument();
    expect(screen.getByTitle('Remove port "in_2"')).toBeInTheDocument();
  });

  it("hides the + control at the max input count (ADR-029 limit)", () => {
    renderVariadic({ max_input_ports: 2 });
    expect(screen.queryByTitle("Add input port")).toBeNull();
  });

  it("hides remove controls at the min input count (ADR-029 limit)", () => {
    renderNode({
      category: "process",
      blockType: "data_router",
      config: { input_ports: [{ name: "in_1", types: ["DataObject"] }] },
      inputPorts: [makePort("in_1", "input")],
      schema: makeSchema({
        variadic_inputs: true,
        min_input_ports: 1,
        max_input_ports: 4,
        input_ports: [],
      }),
    });
    expect(screen.queryByTitle('Remove port "in_1"')).toBeNull();
  });

  it("opens the add-port dialog from the rail + control", () => {
    renderVariadic();
    fireEvent.click(screen.getByTitle("Add input port"));
    expect(screen.getByTestId("add-port-dialog")).toBeInTheDocument();
  });

  it("persists a new port through onUpdateConfig.input_ports", () => {
    const onUpdateConfig = vi.fn();
    renderNode({
      category: "process",
      blockType: "data_router",
      onUpdateConfig,
      config: { input_ports: [{ name: "in_1", types: ["DataObject"] }] },
      inputPorts: [makePort("in_1", "input")],
      schema: makeSchema({
        variadic_inputs: true,
        min_input_ports: 1,
        max_input_ports: 4,
        input_ports: [],
        allowed_input_types: ["DataObject"],
      }),
    });
    fireEvent.click(screen.getByTitle("Add input port"));
    fireEvent.click(screen.getByTestId("add-port-submit"));
    expect(onUpdateConfig).toHaveBeenCalledTimes(1);
    const patch = onUpdateConfig.mock.calls[0][0] as { input_ports: Array<{ name: string }> };
    expect(patch.input_ports).toHaveLength(2);
    expect(patch.input_ports[1].name).toBe("port_2");
  });
});

describe("BlockNode — port handle offset (owner UX: ports not flush to border)", () => {
  it("offsets input/output handles outside the node body", () => {
    const { container } = renderNode({
      inputPorts: [makePort("in", "input", ["DataObject"])],
      outputPorts: [makePort("out", "output", ["DataObject"])],
      schema: makeSchema({
        input_ports: [makePort("in", "input", ["DataObject"])],
        output_ports: [makePort("out", "output", ["DataObject"])],
      }),
    });
    const inHandle = container.querySelector('[data-handleid="in"]') as HTMLElement | null;
    const outHandle = container.querySelector('[data-handleid="out"]') as HTMLElement | null;
    expect(inHandle).not.toBeNull();
    expect(outHandle).not.toBeNull();
    // -10 leaves a small gap between the port dot and the node border.
    expect(inHandle?.style.left).toBe("-10px");
    expect(outHandle?.style.right).toBe("-10px");
  });
});
