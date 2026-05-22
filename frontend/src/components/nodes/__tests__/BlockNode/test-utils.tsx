// Shared test fixtures + helpers extracted from BlockNode.test.tsx as part
// of the #1422 god-file split. Each downstream test file imports `renderNode`
// + the `make*` helpers + the api mock setup from here so the test file can
// stay focused on a single behavior surface.

import { render } from "@testing-library/react";
import { vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { BlockNode } from "../../BlockNode";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  DynamicPortsConfig,
  FormatCapabilityResponse,
} from "../../../../types/api";
import type { BlockNodeData } from "../../../../types/ui";

// api module mock — browse endpoints removed (#467), stub for remaining
// tests. `openNativeDialog` is a `vi.fn()` so individual tests can stub it
// per-case. Tests that need the mock import `openNativeDialogMock` from
// here and call `.mockReset()` in their own afterEach.
export const openNativeDialogMock = vi.fn();
vi.mock("../../../../lib/api", () => ({
  api: {
    get openNativeDialog() {
      return openNativeDialogMock;
    },
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  },
}));

export function makePort(
  name: string,
  direction: "input" | "output",
  accepted: string[] = ["DataObject"],
): BlockPortResponse {
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

export function makeSchema(overrides: Partial<BlockSchemaResponse> = {}): BlockSchemaResponse {
  return {
    name: "Test Block",
    type_name: "test_block",
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [],
    output_ports: [],
    config_schema: { type: "object", properties: {} },
    type_hierarchy: [],
    dynamic_ports: null,
    direction: null,
    ...overrides,
  };
}

export function makeCapability(
  overrides: Partial<FormatCapabilityResponse> = {},
): FormatCapabilityResponse {
  return {
    id: "imaging.image.tiff.load",
    direction: "load",
    data_type: "Image",
    format_id: "tiff",
    extensions: [".tif", ".tiff"],
    label: "TIFF",
    block_type: "LoadImage",
    handler: "load",
    is_default: false,
    priority: 0,
    roundtrip_group: null,
    metadata_fidelity: {
      level: "typed_meta",
      typed_meta_reads: ["axes"],
      typed_meta_writes: [],
      format_metadata_reads: [],
      format_metadata_writes: [],
      notes: null,
    },
    is_synthesized: false,
    migration_scaffold: false,
    ...overrides,
  };
}

export function renderNode(dataOverrides: Partial<BlockNodeData> = {}, selected = false) {
  const baseData: BlockNodeData = {
    label: "Test Block",
    blockType: "test_block",
    category: "process",
    inputPorts: [],
    outputPorts: [],
    config: {},
    schema: makeSchema(),
  };
  const props = {
    id: "node-1",
    type: "block",
    data: { ...baseData, ...dataOverrides },
    selected,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
  } as Parameters<typeof BlockNode>[0];

  return render(
    <ReactFlowProvider>
      <BlockNode {...props} />
    </ReactFlowProvider>,
  );
}

// LoadData-style dynamic descriptor mirrored from
// src/scistudio/blocks/io/loaders/load_data.py
export const LOAD_DATA_DYNAMIC: DynamicPortsConfig = {
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

export const LOAD_DATA_CONFIG_SCHEMA = {
  type: "object",
  properties: {
    core_type: {
      type: "string",
      enum: ["Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"],
      default: "DataFrame",
      ui_priority: 0,
    },
    path: { type: "string", ui_priority: 1 },
  },
};

// SaveData-style dynamic descriptor (input_port_mapping + direction="output")
export const SAVE_DATA_DYNAMIC: DynamicPortsConfig = {
  source_config_key: "core_type",
  input_port_mapping: {
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

// Helper: dispatch a real input/change event that React's controlled-input
// tracker will recognise. Setting `input.value = "..."` directly does NOT
// trigger React's onChange because React tracks the previous value on a
// special internal property — bypass via the native HTMLInputElement value
// setter, then dispatch a bubbling "input" event.
export function reactNativeInputChange(
  input: HTMLInputElement,
  newValue: string,
  caret: number,
): void {
  const proto = Object.getPrototypeOf(input);
  const valueSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (!valueSetter) {
    throw new Error("HTMLInputElement value setter not found");
  }
  valueSetter.call(input, newValue);
  // Setting the value clears selection; restore it BEFORE dispatching so
  // the production onChange handler sees the post-edit caret position.
  input.setSelectionRange(caret, caret);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
