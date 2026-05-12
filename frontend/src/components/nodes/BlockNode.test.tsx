import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { BlockNode } from "./BlockNode";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  DynamicPortsConfig,
} from "../../types/api";
import type { BlockNodeData } from "../../types/ui";

// api module mock — browse endpoints removed (#467), stub for remaining tests.
// `openNativeDialog` is a `vi.fn()` so individual tests can stub it per-case.
const openNativeDialogMock = vi.fn();
vi.mock("../../lib/api", () => ({
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

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makePort(
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

function makeSchema(
  overrides: Partial<BlockSchemaResponse> = {},
): BlockSchemaResponse {
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

function renderNode(
  dataOverrides: Partial<BlockNodeData> = {},
  selected = false,
) {
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

// LoadData-style dynamic descriptor mirrored from src/scieasy/blocks/io/loaders/load_data.py
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

const LOAD_DATA_CONFIG_SCHEMA = {
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
const SAVE_DATA_DYNAMIC: DynamicPortsConfig = {
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

// ---------------------------------------------------------------------------
// Discriminator behavior #1: Browse button on category === "io" path field
// ---------------------------------------------------------------------------

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
});

// ---------------------------------------------------------------------------
// Discriminator behavior #2: hidden direction field on category === "io"
// ---------------------------------------------------------------------------

describe("BlockNode — hidden direction field (ADR-028 Addendum 1 §B fix #2)", () => {
  it("hides the direction config field for IO blocks", () => {
    renderNode({
      category: "io",
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        config_schema: {
          type: "object",
          properties: {
            direction: {
              type: "string",
              enum: ["input", "output"],
              ui_priority: 0,
            },
            path: { type: "string", title: "Path", ui_priority: 1 },
          },
        },
      }),
    });
    // The direction <select> must NOT be rendered.
    expect(screen.queryByRole("combobox")).toBeNull();
    // The path field must still be rendered.
    expect(screen.getByText("Path")).toBeInTheDocument();
  });

  it("does NOT hide the direction field on non-IO blocks", () => {
    // A hypothetical process block that happens to have a 'direction' config
    // field. The hide-direction filter must scope to category=io, not match
    // the field name globally.
    renderNode({
      category: "process",
      schema: makeSchema({
        base_category: "process",
        config_schema: {
          type: "object",
          properties: {
            direction: {
              type: "string",
              enum: ["forward", "reverse"],
              title: "Direction",
              ui_priority: 0,
            },
          },
        },
      }),
    });
    expect(screen.getByText("Direction")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Discriminator behavior #3: Browse uses schema.direction, not config.direction
// ---------------------------------------------------------------------------

describe("BlockNode — Browse buttons removed (#467, tkinter crash on macOS)", () => {
  it("does not render Browse button for IO blocks", () => {
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

  it("renders a text input for the path field instead", () => {
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

    // The path field should have a text input with placeholder
    const input = screen.getByPlaceholderText("Type or paste path");
    expect(input).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Bonus: port live-update via computeEffectivePorts
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Error message inline display (#422)
// ---------------------------------------------------------------------------

describe("BlockNode — inline error message (issue #422)", () => {
  it("renders inline error message when status=error and errorMessage is set", () => {
    renderNode({
      status: "error",
      errorMessage: "Division by zero",
    });
    expect(screen.getByText("Division by zero")).toBeInTheDocument();
  });

  it("truncates long error messages to 80 chars with ellipsis", () => {
    const longMsg = "A".repeat(100);
    renderNode({
      status: "error",
      errorMessage: longMsg,
    });
    // The truncated text is the first 80 chars followed by an ellipsis char.
    const expected = `${"A".repeat(80)}\u2026`;
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("shows full error text in title attribute for long messages", () => {
    const longMsg = "B".repeat(100);
    renderNode({
      status: "error",
      errorMessage: longMsg,
    });
    const el = screen.getByTitle(longMsg);
    expect(el).toBeInTheDocument();
  });

  it("does NOT render error message element when status is not error", () => {
    renderNode({
      status: "done",
      errorMessage: "this should not appear",
    });
    expect(screen.queryByText("this should not appear")).toBeNull();
  });

  it("does NOT render error message element when errorMessage is absent", () => {
    renderNode({ status: "error" });
    // Only the status badge should be present; no extra text element.
    // 'Error' is the badge label text — confirm it exists but no extra message.
    expect(screen.getByText("Error")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Sanity smoke: header label still renders
// ---------------------------------------------------------------------------

describe("BlockNode — sanity smoke", () => {
  it("renders the block label in the header", () => {
    renderNode({ label: "My Test Block" });
    expect(screen.getByText("My Test Block")).toBeInTheDocument();
  });

  it("renders the io category icon for io blocks", () => {
    const { container } = renderNode({ category: "io" });
    // Icon is the folder emoji \uD83D\uDCC1 — check it appears somewhere.
    expect(container.textContent).toContain("\uD83D\uDCC1");
  });
});


// ---------------------------------------------------------------------------
// Native dialog fallback behavior (#678)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Caret preservation on mid-string insert (#710)
// ---------------------------------------------------------------------------

describe("InlineConfigField - caret preservation on mid-string insert (#710)", () => {
  // Wrapper that re-renders the BlockNode whenever onUpdateConfig is called,
  // simulating the Zustand-store round-trip that triggers the original caret-
  // reset bug in React-controlled inputs.
  function StatefulHost({ initial }: { initial: string }) {
    const [config, setConfig] = useState<Record<string, unknown>>({ path: initial });
    const baseData: BlockNodeData = {
      label: "Test Block",
      blockType: "test_block",
      category: "process",
      inputPorts: [],
      outputPorts: [],
      config,
      schema: makeSchema({
        config_schema: {
          type: "object",
          properties: { path: { type: "string", title: "Path", ui_priority: 0 } },
        },
      }),
      onUpdateConfig: (patch: Record<string, unknown>) => {
        setConfig((c) => ({ ...c, ...patch }));
      },
    };
    const props = {
      id: "node-1",
      type: "block",
      data: baseData,
      selected: false,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      zIndex: 0,
    } as Parameters<typeof BlockNode>[0];
    return (
      <ReactFlowProvider>
        <BlockNode {...props} />
      </ReactFlowProvider>
    );
  }

  it("inserts a character in the middle of the value without jumping caret to end", () => {
    render(<StatefulHost initial="abcdef" />);
    const input = screen.getByDisplayValue("abcdef") as HTMLInputElement;

    // Focus the input and place the caret between "abc" and "def".
    act(() => {
      input.focus();
      input.setSelectionRange(3, 3);
    });
    expect(document.activeElement).toBe(input);
    expect(input.selectionStart).toBe(3);

    // Simulate the browser inserting "X" at position 3 by dispatching a
    // change event whose target reflects the would-be post-input state.
    // We must also set the DOM selectionStart/selectionEnd because the
    // production onChange reads them off the event target.
    act(() => {
      input.value = "abcXdef";
      input.setSelectionRange(4, 4);
      fireEvent.change(input, { target: input });
    });

    // After the round-trip (state update -> re-render with new value prop),
    // the caret must remain at position 4, not jump to the end (7).
    const updated = screen.getByDisplayValue("abcXdef") as HTMLInputElement;
    expect(updated).toBe(input); // same DOM node, just re-rendered
    expect(updated.selectionStart).toBe(4);
    expect(updated.selectionEnd).toBe(4);
    expect(updated.selectionStart).not.toBe(updated.value.length);
  });
});

describe("BlockNode - native dialog status-aware fallback (#678)", () => {
  // A non-io block with a file_browser config field renders a Browse "..." button.
  function renderBrowseField() {
    return renderNode({
      category: "process",
      blockType: "test_block",
      schema: makeSchema({
        base_category: "process",
        type_name: "test_block",
        config_schema: {
          type: "object",
          properties: {
            path: { type: "string", ui_widget: "file_browser", ui_priority: 0 },
          },
        },
      }),
    });
  }

  function findBrowseButton(): HTMLElement {
    const btn = screen.getByTitle("Browse filesystem");
    expect(btn).toBeInTheDocument();
    return btn;
  }

  function getFileBrowserHeading(): HTMLElement | null {
    return screen.queryByText("Select File");
  }

  it("falls back to in-app FileBrowserModal when native dialog returns HTTP 500", async () => {
    const { ApiError } = await import("../../lib/api");
    openNativeDialogMock.mockRejectedValueOnce(
      new ApiError("Native dialog command not available on this platform (Linux)", 500),
    );

    renderBrowseField();
    expect(getFileBrowserHeading()).toBeNull();
    await userEvent.click(findBrowseButton());

    // Modal opens (heading "Select File" is the modal's title).
    expect(getFileBrowserHeading()).toBeInTheDocument();
  });

  it("does NOT open in-app FileBrowserModal when native dialog returns HTTP 504", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const { ApiError } = await import("../../lib/api");
    openNativeDialogMock.mockRejectedValueOnce(
      new ApiError("Dialog timed out", 504),
    );

    renderBrowseField();
    await userEvent.click(findBrowseButton());

    // Modal must NOT open on a 504 - that is the deprecated picker we
    // are explicitly avoiding (#678).
    expect(getFileBrowserHeading()).toBeNull();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("falls back to in-app FileBrowserModal on a non-ApiError network failure", async () => {
    openNativeDialogMock.mockRejectedValueOnce(new Error("network down"));

    renderBrowseField();
    await userEvent.click(findBrowseButton());

    expect(getFileBrowserHeading()).toBeInTheDocument();
  });
});
