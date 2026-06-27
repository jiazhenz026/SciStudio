import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FormatCapabilityResponse } from "../../types/api";
import { ConfigPanel } from "./ConfigPanel";

const apiMocks = vi.hoisted(() => ({
  browseFilesystem: vi.fn(),
  openNativeDialog: vi.fn(),
  // CapabilityDropdown (rendered by PortEditorTable / CodeBlock port table)
  // fetches capabilities via ``listCapabilities`` → ``api.listBlocks`` inside
  // an effect; stub it so those effects resolve cleanly in tests.
  listBlocks: vi.fn().mockResolvedValue({ blocks: [] }),
}));

vi.mock("../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  },
  // ADR-044: ConfigPanel now imports SubworkflowConfigEditor, which pulls in the
  // zustand store; the store's initializer calls setWorkflowWriteStartedListener
  // from this module, so the mock must export it (no-op) to instantiate.
  setWorkflowWriteStartedListener: vi.fn(),
  api: {
    browseFilesystem: apiMocks.browseFilesystem,
    openNativeDialog: apiMocks.openNativeDialog,
    listBlocks: apiMocks.listBlocks,
  },
}));

function makeCapability(
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
      level: "pixel_only",
      typed_meta_reads: [],
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

describe("ConfigPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.browseFilesystem.mockReset();
    apiMocks.openNativeDialog.mockReset();
  });

  it("uses user-friendly empty state copy", () => {
    render(<ConfigPanel onUpdateConfig={() => {}} selectedNode={null} />);

    expect(screen.getByText("Select a block to edit its settings.")).toBeInTheDocument();
    expect(screen.queryByText(/JSON|schema/i)).toBeNull();
  });

  it("uses the native dialog first from the config Browse button", async () => {
    const onUpdateConfig = vi.fn();
    apiMocks.openNativeDialog.mockResolvedValueOnce({
      paths: ["C:\\Users\\jiazh\\image.tif"],
    });

    render(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: { params: { path: "C:\\Users\\jiazh\\old.tif" } },
        }}
        schema={{
          name: "Load",
          type_name: "load_data",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "input",
          config_schema: {
            properties: {
              path: {
                type: "string",
                title: "Path",
                ui_priority: 0,
                ui_widget: "file_browser",
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );

    fireEvent.click(screen.getByTitle("Browse filesystem"));

    await waitFor(() =>
      expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", "C:\\Users\\jiazh"),
    );
    await waitFor(() =>
      expect(onUpdateConfig).toHaveBeenCalledWith({ path: "C:\\Users\\jiazh\\image.tif" }),
    );
    expect(apiMocks.browseFilesystem).not.toHaveBeenCalled();
  });

  it("seeds browse from the first path when a multi-file field holds an array (#1753)", async () => {
    // A multi-select file field stores an array. Re-browsing must start from the
    // first file's directory, NOT String(array) — a comma-joined concatenation
    // of every path that builds an over-length path and 500s the backend.
    apiMocks.openNativeDialog.mockResolvedValueOnce({ paths: [] });

    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: {
            params: {
              path: [
                "/data/imaging/LA0Hr.txt",
                "/data/imaging/LA1Hr.txt",
                "/data/imaging/LA2Hr.txt",
              ],
            },
          },
        }}
        schema={{
          name: "Load",
          type_name: "load_data",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "input",
          config_schema: {
            properties: {
              path: {
                type: "array",
                title: "Path",
                ui_priority: 0,
                ui_widget: "file_browser",
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );

    fireEvent.click(screen.getByTitle("Browse filesystem"));

    await waitFor(() =>
      expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", "/data/imaging"),
    );
    // The seeded directory must be a single real path, never a comma-joined blob.
    const [, initialDir] = apiMocks.openNativeDialog.mock.calls[0];
    expect(initialDir).not.toContain(",");
  });

  it("falls back to the in-app file browser when native dialog fails", async () => {
    const { ApiError } = await import("../../lib/api");
    apiMocks.openNativeDialog.mockRejectedValueOnce(
      new ApiError("Native dialog command not available on this platform", 500),
    );
    apiMocks.browseFilesystem.mockResolvedValueOnce({
      path: "C:\\Users\\jiazh",
      entries: [],
    });

    render(
      <ConfigPanel
        onUpdateConfig={() => {}}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: { params: { path: "" } },
        }}
        schema={{
          name: "Load",
          type_name: "load_data",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "input",
          config_schema: {
            properties: {
              path: {
                type: "string",
                title: "Path",
                ui_priority: 0,
                ui_widget: "file_browser",
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );

    fireEvent.click(screen.getByTitle("Browse filesystem"));

    expect(await screen.findByText("Select File")).toBeInTheDocument();
    expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", undefined);
    expect(apiMocks.browseFilesystem).toHaveBeenCalledWith("");
  });

  it("renders core IO fields as Path, Type, Format and inherits parent-type formats", () => {
    const onUpdateConfig = vi.fn();

    render(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: { params: { core_type: "SRSImage", capability_id: "imaging.image.tiff.load" } },
        }}
        schema={{
          name: "Load",
          type_name: "load_data",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "input",
          config_schema: {
            properties: {
              path: { type: "string", title: "Path", ui_priority: 0 },
              core_type: {
                type: "string",
                title: "Type",
                enum: ["DataFrame", "Image", "SRSImage"],
                default: "DataFrame",
                ui_priority: 1,
              },
            },
          },
          type_hierarchy: [
            { name: "DataObject", base_type: "", description: "" },
            { name: "Array", base_type: "DataObject", description: "" },
            { name: "Image", base_type: "Array", description: "" },
            { name: "SRSImage", base_type: "Image", description: "" },
          ],
          format_capabilities: [
            makeCapability({
              id: "core.dataframe.csv.load",
              data_type: "DataFrame",
              format_id: "csv",
              extensions: [".csv"],
              label: "CSV",
            }),
            makeCapability({ id: "imaging.image.tiff.load" }),
          ],
        }}
      />,
    );

    const pathField = screen.getByLabelText("Path");
    const typeField = screen.getByLabelText("Type");
    const formatField = screen.getByLabelText("Format");
    expect(pathField.compareDocumentPosition(typeField)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(typeField.compareDocumentPosition(formatField)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.getByRole("option", { name: /TIFF/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /CSV/ })).toBeNull();

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "DataFrame" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ core_type: "DataFrame", capability_id: null });
  });

  it("renders Artifact core IO as a single Any format", () => {
    render(
      <ConfigPanel
        onUpdateConfig={() => {}}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: { params: { core_type: "Artifact" } },
        }}
        schema={{
          name: "Load",
          type_name: "load_data",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "input",
          config_schema: {
            properties: {
              path: { type: "string", title: "Path", ui_priority: 0 },
              core_type: {
                type: "string",
                title: "Type",
                enum: ["DataFrame", "Artifact"],
                default: "DataFrame",
                ui_priority: 1,
              },
            },
          },
          type_hierarchy: [
            { name: "DataObject", base_type: "", description: "" },
            { name: "Artifact", base_type: "DataObject", description: "" },
          ],
          format_capabilities: [
            makeCapability({
              id: "core.artifact.binary.load",
              data_type: "Artifact",
              format_id: "binary",
              extensions: [".bin"],
              label: "Binary",
            }),
            makeCapability({
              id: "core.artifact.pdf.load",
              data_type: "Artifact",
              format_id: "pdf",
              extensions: [".pdf"],
              label: "PDF",
            }),
          ],
        }}
      />,
    );

    const formatField = screen.getByLabelText("Format") as HTMLSelectElement;
    expect(formatField).toBeDisabled();
    expect(screen.getByRole("option", { name: "Any" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Binary/ })).toBeNull();
    expect(screen.queryByRole("option", { name: /PDF/ })).toBeNull();
    expect(screen.getByText("Artifact / any / pixel_only")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // ADR-050 SC-003 — BottomPanel Config owns ALL computational config after
  // the inline node-config strip is removed by FE-1. These tests prove the
  // panel still surfaces every control the node body used to: core type,
  // format capability, file path (covered above), CodeBlock editing, and
  // full variadic port editing (naming + type selection + add/remove).
  // -------------------------------------------------------------------------

  it("renders the variadic port editor with naming, type selection, and add/remove (SC-003)", () => {
    const onUpdateConfig = vi.fn();

    render(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "merge-1",
          block_type: "merge",
          config: {
            params: {
              input_ports: [
                { name: "a", types: ["Image"] },
                { name: "b", types: ["Image"] },
              ],
            },
          },
        }}
        schema={{
          name: "Merge",
          type_name: "merge",
          base_category: "process",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          variadic_inputs: true,
          min_input_ports: 1,
          max_input_ports: 4,
          allowed_input_types: ["Image", "DataFrame"],
          config_schema: { properties: {} },
          type_hierarchy: [
            { name: "DataObject", base_type: "", description: "" },
            { name: "Image", base_type: "DataObject", description: "" },
            { name: "DataFrame", base_type: "DataObject", description: "" },
          ],
        }}
      />,
    );

    // Port editor heading + name inputs prove BottomPanel owns full port editing.
    expect(screen.getByText("Input Ports")).toBeInTheDocument();
    const nameInputs = screen.getAllByPlaceholderText("port name") as HTMLInputElement[];
    expect(nameInputs).toHaveLength(2);
    expect(nameInputs[0].value).toBe("a");

    // Type selection is editable per port.
    const typeSelects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    fireEvent.change(typeSelects[0], { target: { value: "DataFrame" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      input_ports: [
        { name: "a", types: ["DataFrame"], capability_id: null },
        { name: "b", types: ["Image"] },
      ],
    });

    // Add Port appends a new row through the input_ports config.
    onUpdateConfig.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Add Port/ }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      input_ports: [
        { name: "a", types: ["Image"] },
        { name: "b", types: ["Image"] },
        { name: "port_3", types: ["Image"] },
      ],
    });
  });

  it("renders the interaction-memory toggle for interactive blocks (ADR-051 Addendum 1)", () => {
    const onUpdateConfig = vi.fn();

    const interactiveSchema = {
      name: "Data Router",
      type_name: "data_router",
      base_category: "process",
      subcategory: "routing",
      description: "",
      version: "1",
      input_ports: [],
      output_ports: [],
      execution_mode: "interactive",
      config_schema: { properties: {} },
      type_hierarchy: [],
    };

    const { rerender } = render(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{ id: "dr-1", block_type: "data_router", config: { params: {} } }}
        schema={interactiveSchema}
      />,
    );

    // Generic toggle is present (rendered from execution_mode, not per-block).
    const checkbox = screen.getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    expect(screen.getByText(/Remember my choice and skip this dialog/)).toBeInTheDocument();

    fireEvent.click(checkbox);
    expect(onUpdateConfig).toHaveBeenCalledWith({
      interactive_memory: { enabled: true, decision: null, signature: null },
    });

    // With a saved decision, "Choose again" clears it (keeps memory enabled).
    onUpdateConfig.mockClear();
    rerender(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "dr-1",
          block_type: "data_router",
          config: {
            params: {
              interactive_memory: {
                enabled: true,
                decision: { assignments: { port_1: ["input_1:0"] } },
                signature: { input_1: ["a.txt"] },
              },
            },
          },
        }}
        schema={interactiveSchema}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Choose again/ }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      interactive_memory: { enabled: true, decision: null, signature: null },
    });
  });

  it("omits the interaction-memory toggle for non-interactive blocks", () => {
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{ id: "n", block_type: "x", config: { params: {} } }}
        schema={{
          name: "X",
          type_name: "x",
          base_category: "process",
          subcategory: "",
          description: "",
          version: "1",
          input_ports: [],
          output_ports: [],
          execution_mode: "auto",
          config_schema: { properties: {} },
          type_hierarchy: [],
        }}
      />,
    );
    expect(screen.queryByText(/Remember my choice and skip this dialog/)).not.toBeInTheDocument();
  });

  it("renders the CodeBlock config editor in BottomPanel (SC-003)", () => {
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: { params: { code: "print('hi')", inputs: [], outputs: [] } },
        }}
        schema={{
          name: "Code Block",
          type_name: "code_block",
          base_category: "code",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          config_schema: { properties: {} },
          type_hierarchy: [],
        }}
      />,
    );

    // The CodeBlock branch renders its dedicated editor (declared input/output
    // port tables + script path) rather than the generic schema-field grid —
    // proving CodeBlock config lives in BottomPanel, not on the canvas node.
    expect(screen.getByText("Declared inputs")).toBeInTheDocument();
    expect(screen.getByText("Declared outputs")).toBeInTheDocument();
    expect(screen.getByText("Script path")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // ADR-050 FR-014 — lossy-save warning detail. The canvas square node no
  // longer renders this chip; BottomPanel Config is the sole surface for it.
  // -------------------------------------------------------------------------

  const saveSchema = () => ({
    name: "Save",
    type_name: "save_data",
    base_category: "io",
    subcategory: "",
    description: "",
    version: "0.1.0",
    input_ports: [],
    output_ports: [],
    direction: "output" as const,
    config_schema: {
      properties: {
        path: { type: "string", title: "Path", ui_priority: 0 },
      },
    },
    type_hierarchy: [{ name: "Image", base_type: "DataObject", description: "" }],
    format_capabilities: [
      makeCapability({
        id: "imaging.image.png.save",
        direction: "save",
        data_type: "Image",
        format_id: "png",
        extensions: [".png"],
        label: "PNG",
        // pixel_only: drops every OME field.
        metadata_fidelity: {
          level: "pixel_only",
          typed_meta_reads: [],
          typed_meta_writes: [],
          format_metadata_reads: [],
          format_metadata_writes: [],
          notes: null,
        },
      }),
    ],
  });

  const upstreamImageOutputs = {
    "load-1": {
      output: {
        metadata: { meta: { ome: { images: [{ pixels: { physical_size_x: 0.5 } }] } } },
      },
    },
  };

  it("renders the lossy-save warning detail for a selected save node (FR-014)", () => {
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "save-1",
          block_type: "save_data",
          config: { params: { path: "out.png", capability_id: "imaging.image.png.save" } },
        }}
        schema={saveSchema()}
        edges={[{ source: "load-1:output", target: "save-1:input" }]}
        blockOutputs={upstreamImageOutputs}
      />,
    );

    const detail = screen.getByTestId("config-lossy-save-detail");
    expect(detail).toBeInTheDocument();
    expect(within(detail).getByTestId("lossy-save-warning")).toBeInTheDocument();
    expect(within(detail).getByText(/Lossy save/)).toBeInTheDocument();
  });

  it("omits the lossy-save detail when the capability round-trips losslessly (FR-014)", () => {
    const schema = saveSchema();
    schema.format_capabilities[0].id = "imaging.image.ome.save";
    schema.format_capabilities[0].metadata_fidelity = {
      level: "lossless",
      typed_meta_reads: [],
      typed_meta_writes: [],
      format_metadata_reads: [],
      format_metadata_writes: [],
      notes: null,
    };

    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "save-1",
          block_type: "save_data",
          config: { params: { path: "out.ome.tiff", capability_id: "imaging.image.ome.save" } },
        }}
        schema={schema}
        edges={[{ source: "load-1:output", target: "save-1:input" }]}
        blockOutputs={upstreamImageOutputs}
      />,
    );

    expect(screen.queryByTestId("config-lossy-save-detail")).toBeNull();
  });

  it("degrades gracefully (no lossy detail) when blockOutputs/edges are absent (FR-014)", () => {
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "save-1",
          block_type: "save_data",
          config: { params: { path: "out.png", capability_id: "imaging.image.png.save" } },
        }}
        schema={saveSchema()}
      />,
    );

    // The panel still renders config controls without the optional wiring.
    expect(screen.getByLabelText("Path")).toBeInTheDocument();
    expect(screen.queryByTestId("config-lossy-save-detail")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// ADR-050 SC-002 — no production import path in the BottomPanel config surface
// references the deleted inline-node-config modules. This guards the
// config-ownership seam: config lives in BottomPanel, never inline on the node.
// ---------------------------------------------------------------------------
describe("BottomPanel config surface — no inline-config imports (SC-002)", () => {
  const ownedFiles = [
    "BottomPanel.tsx",
    "BottomPanel.parts/ConfigPanel.tsx",
    "BottomPanel.parts/FormatCapabilityConfig.tsx",
    "BottomPanel.parts/TabBar.tsx",
    "WorkflowEditor/LossySaveWarning.tsx",
    "PortEditorTable.tsx",
    "PortEditor/CapabilityDropdown.tsx",
  ];

  const forbidden = [
    "InlineConfigField",
    "InlineTextInputField",
    "InlineCapabilitySelector",
    "inlineConfigHelpers",
  ];

  it("none of the config-surface source files import inline-node-config modules", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    // Vitest runs with cwd = frontend/ (vite.config.ts uses ./-relative paths),
    // so resolve the owned source files under src/components from there.
    const componentsDir = join(process.cwd(), "src", "components");
    for (const relative of ownedFiles) {
      const source = readFileSync(join(componentsDir, relative), "utf8");
      for (const token of forbidden) {
        expect(source, `${relative} must not reference ${token}`).not.toContain(token);
      }
    }
  });
});
