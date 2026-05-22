// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
// Covers ADR-028 Addendum 1 §D4 — dynamic-port live-update + Browse-button
// removal (#467) on IO blocks (which lives next to the port behavior in
// terms of the schema-driven discriminator).

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

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

describe("BlockNode — Browse buttons removed (#467, tkinter crash on macOS)", () => {
  it("does NOT render Browse button for category=io with a path config field", () => {
    renderNode({
      category: "io",
      blockType: "load_data",
      schema: makeSchema({
        base_category: "io",
        type_name: "load_data",
        direction: "input",
        config_schema: {
          type: "object",
          properties: { path: { type: "string", ui_priority: 0 } },
        },
      }),
    });
    expect(screen.queryByRole("button", { name: /Browse/i })).toBeNull();
  });

  it("renders a text input with placeholder for IO path fields", () => {
    renderNode({
      category: "io",
      blockType: "load_image",
      schema: makeSchema({
        base_category: "io",
        type_name: "load_image",
        direction: "input",
        config_schema: {
          type: "object",
          properties: { path: { type: "string" } },
        },
      }),
    });
    expect(screen.queryByRole("button", { name: /Browse/i })).toBeNull();
    expect(screen.getByPlaceholderText("Type or paste path")).toBeDefined();
  });

  it("does not render Browse button for save-direction IO blocks", () => {
    renderNode({
      category: "io",
      blockType: "save_data",
      schema: makeSchema({
        base_category: "io",
        type_name: "save_data",
        direction: "output",
        config_schema: {
          type: "object",
          properties: { path: { type: "string", ui_priority: 0 } },
        },
      }),
    });

    expect(screen.queryByRole("button", { name: /Browse/i })).toBeNull();
  });
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
    // The Handle's title attribute embeds the accepted_types list — that is
    // the load-bearing piece of information for the audit agent here.
    const handles = container.querySelectorAll('[data-handleid="data"]');
    expect(handles.length).toBeGreaterThan(0);
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("Array"))).toBe(true);
    // The placeholder DataObject type must NOT be visible — the dynamic
    // override has replaced it.
    expect(titles.some((t) => t.includes("DataObject"))).toBe(false);
  });

  it("renders the LoadData output port with accepted_types=['DataFrame'] when core_type=DataFrame", () => {
    const { container } = renderLoadData("DataFrame");
    const handles = container.querySelectorAll('[data-handleid="data"]');
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    expect(titles.some((t) => t.includes("DataFrame"))).toBe(true);
    expect(titles.some((t) => t.includes("DataObject"))).toBe(false);
  });

  it("falls back to the placeholder type when core_type is unset", () => {
    // Static block path: no core_type in config means no override applies.
    const { container } = renderNode({
      category: "io",
      blockType: "load_data",
      config: {}, // no core_type
      outputPorts: [makePort("data", "output", ["DataObject"])],
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        output_ports: [makePort("data", "output", ["DataObject"])],
        dynamic_ports: LOAD_DATA_DYNAMIC,
      }),
    });
    const handles = container.querySelectorAll('[data-handleid="data"]');
    const titles = Array.from(handles).map((h) => h.getAttribute("title") ?? "");
    // Title format changed in #445: now shows primary type name, not "portName: typeList"
    expect(titles.some((t) => t.includes("DataObject"))).toBe(true);
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
