// Tests for the #1326 PortInfoPanel render rules.
//
// Spec: docs/specs/port-description-metadata.md.
//
// Row format rules under test:
//   - Author-defined port with non-empty description → `[icon] Type — description`
//   - Author-defined port with empty description → `[icon] Type` (no em-dash)
//   - User-added variadic port (name NOT in schema-declared set) → `[icon] Type — name`

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BlockPortResponse, BlockSchemaResponse } from "../../types/api";

import { PortInfoPanel } from "./PortInfoPanel";

const TYPE_HIERARCHY = [
  { name: "DataObject", base_type: null, description: "" },
  { name: "Image", base_type: "DataObject", description: "" },
];

function port(name: string, description = "", types: string[] = ["DataObject"]): BlockPortResponse {
  return {
    name,
    direction: "input",
    accepted_types: types,
    required: true,
    description,
    constraint_description: "",
    is_collection: false,
  };
}

function schema(partial: Partial<BlockSchemaResponse> = {}): BlockSchemaResponse {
  return {
    name: "TestBlock",
    description: "",
    base_category: "process",
    subcategory: null,
    input_ports: [],
    output_ports: [],
    config_schema: {},
    allowed_input_types: [],
    allowed_output_types: [],
    variadic_inputs: false,
    variadic_outputs: false,
    type_hierarchy: TYPE_HIERARCHY,
    dynamic_ports: null,
    min_input_ports: null,
    max_input_ports: null,
    min_output_ports: null,
    max_output_ports: null,
    format_capabilities: [],
    metadata_fidelity: { level: "pixel_only", typed_meta_reads: [], typed_meta_writes: [], format_metadata_reads: [], format_metadata_writes: [] },
    ...partial,
  };
}

describe("PortInfoPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders type + description for author-defined ports with descriptions", () => {
    const declared = port("data", "Declared v2 inputs");
    render(
      <PortInfoPanel
        inputPorts={[declared]}
        outputPorts={[]}
        schema={schema({ input_ports: [declared] })}
      />,
    );

    expect(screen.getByText("DataObject")).toBeInTheDocument();
    expect(screen.getByText("Declared v2 inputs")).toBeInTheDocument();
    // The em-dash separator is present.
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders only type when author-defined port description is empty", () => {
    const declared = port("input", "");
    render(
      <PortInfoPanel
        inputPorts={[declared]}
        outputPorts={[]}
        schema={schema({ input_ports: [declared] })}
      />,
    );

    expect(screen.getByText("DataObject")).toBeInTheDocument();
    // No em-dash row separator when there is no descriptive text.
    expect(screen.queryByText("—")).toBeNull();
    // The port's internal name MUST NOT leak into the panel for
    // empty-description author-defined ports.
    expect(screen.queryByText("input")).toBeNull();
  });

  it("falls back to user-typed name for variadic user-added ports", () => {
    const declared = port("data", "Declared v2 inputs");
    const userAdded = port("raw_image", "", ["Image"]);
    render(
      <PortInfoPanel
        inputPorts={[declared, userAdded]}
        outputPorts={[]}
        // Schema declares ``data`` only — ``raw_image`` is user-added.
        schema={schema({ input_ports: [declared], variadic_inputs: true })}
      />,
    );

    // Author-defined row.
    expect(screen.getByText("Declared v2 inputs")).toBeInTheDocument();
    // Variadic user-added row uses the user-typed name as descriptive text.
    expect(screen.getByText("raw_image")).toBeInTheDocument();
  });

  it("hides empty section headers", () => {
    const declared = port("result", "Output channel");
    render(
      <PortInfoPanel
        inputPorts={[]}
        outputPorts={[declared]}
        schema={schema({ output_ports: [declared] })}
      />,
    );

    expect(screen.queryByText("Input Port")).toBeNull();
    expect(screen.getByText("Output Port")).toBeInTheDocument();
  });

  it("renders nothing when both port lists are empty", () => {
    const { container } = render(
      <PortInfoPanel inputPorts={[]} outputPorts={[]} schema={schema()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
