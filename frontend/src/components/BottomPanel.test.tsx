import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomPanel } from "./BottomPanel";
import type { FormatCapabilityResponse } from "../types/api";

// #1373: hoist api mocks so native-dialog and filesystem-fallback tests can
// control openNativeDialog / browseFilesystem per-test.
const apiMocks = vi.hoisted(() => ({
  openNativeDialog: vi.fn(),
  browseFilesystem: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  },
  api: {
    openNativeDialog: apiMocks.openNativeDialog,
    browseFilesystem: apiMocks.browseFilesystem,
  },
  setWorkflowWriteStartedListener: vi.fn(),
}));

function makeCapability(
  overrides: Partial<FormatCapabilityResponse> = {},
): FormatCapabilityResponse {
  return {
    id: "imaging.image.tiff.save",
    direction: "save",
    data_type: "Image",
    format_id: "tiff",
    extensions: [".tif", ".tiff"],
    label: "TIFF",
    block_type: "SaveImage",
    handler: "save",
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

const codeBlockSchema = {
  name: "Code Block",
  type_name: "code_block",
  base_category: "code",
  subcategory: "",
  description: "",
  version: "0.1.0",
  input_ports: [],
  output_ports: [],
  config_schema: {
    properties: {
      script_path: { type: "string", title: "Project Script" },
      interpreter_mode: { type: "string", enum: ["auto", "existing"] },
      inputs: { type: "array" },
      outputs: { type: "array" },
    },
  },
  type_hierarchy: [],
};

describe("BottomPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.openNativeDialog.mockReset();
    apiMocks.browseFilesystem.mockReset();
  });

  it("renders config inputs from schema and emits config updates", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "node-1",
          block_type: "process_block",
          config: { params: { sleep_seconds: 1 } },
        }}
        selectedSchema={{
          name: "Process Block",
          type_name: "process_block",
          base_category: "process",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          config_schema: {
            properties: {
              sleep_seconds: {
                type: "number",
                title: "Sleep seconds",
                ui_priority: 1,
                default: 0,
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );

    const input = screen.getByDisplayValue("1");
    fireEvent.change(input, { target: { value: "4" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ sleep_seconds: 4 });
  });

  // #793: unread badge appears next to a tab when unreadCount > 0 AND that
  // tab is not the currently-active one. Once the user activates the tab the
  // badge must vanish. (Problems tab was removed; only Logs has a badge now.)
  it("renders an unread badge next to Logs when count > 0 and tab is hidden", () => {
    render(
      <BottomPanel
        activeTab="ai"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={null}
        unreadLogsCount={3}
      />,
    );

    expect(screen.getByTestId("unread-badge-logs")).toHaveTextContent("3");
  });

  it("does not render the unread badge for the currently active tab", () => {
    render(
      <BottomPanel
        activeTab="logs"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={null}
        unreadLogsCount={5}
      />,
    );

    // Logs is active → no badge on logs.
    expect(screen.queryByTestId("unread-badge-logs")).toBeNull();
  });

  it("exposes Terminal as a top-level bottom-panel tab", () => {
    const onTabChange = vi.fn();
    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={onTabChange}
        onUpdateConfig={() => {}}
        selectedNode={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Terminal" }));
    expect(onTabChange).toHaveBeenCalledWith("terminal");
  });

  it("caps the unread badge at 99+", () => {
    render(
      <BottomPanel
        activeTab="ai"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={null}
        unreadLogsCount={250}
      />,
    );

    expect(screen.getByTestId("unread-badge-logs")).toHaveTextContent("99+");
  });

  it("does not render browse buttons for IO path fields (tkinter removed, #467)", () => {
    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={{
          id: "load-1",
          block_type: "imaging.load_image",
          config: { params: { path: "" } },
        }}
        selectedSchema={{
          name: "Load Image",
          type_name: "imaging.load_image",
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
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );

    expect(screen.queryByRole("button", { name: "Browse" })).toBeNull();
  });

  it("renders ADR-043 capability choices and persists capability_id", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "save-1",
          block_type: "imaging.save_image",
          config: { params: {} },
        }}
        selectedSchema={{
          name: "Save Image",
          type_name: "imaging.save_image",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "output",
          config_schema: { properties: {} },
          type_hierarchy: [],
          format_capabilities: [
            makeCapability({ id: "imaging.image.tiff.save", label: "TIFF" }),
            makeCapability({
              id: "imaging.image.png.save",
              extensions: [".png"],
              format_id: "png",
              label: "PNG",
            }),
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "imaging.image.png.save" },
    });

    expect(onUpdateConfig).toHaveBeenCalledWith({
      capability_id: "imaging.image.png.save",
    });
  });

  it("clears ADR-043 capability selection as null when the placeholder is selected", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "save-1",
          block_type: "imaging.save_image",
          config: { params: { capability_id: "imaging.image.tiff.save" } },
        }}
        selectedSchema={{
          name: "Save Image",
          type_name: "imaging.save_image",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "output",
          config_schema: { properties: {} },
          type_hierarchy: [],
          format_capabilities: [
            makeCapability({ id: "imaging.image.tiff.save", label: "TIFF" }),
            makeCapability({
              id: "imaging.image.png.save",
              extensions: [".png"],
              format_id: "png",
              label: "PNG",
            }),
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "" },
    });

    expect(onUpdateConfig).toHaveBeenCalledWith({ capability_id: null });
  });

  it("shows backend-derived ADR-043 warnings for ambiguous lossy choices", () => {
    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={{
          id: "save-1",
          block_type: "imaging.save_image",
          config: { params: {} },
        }}
        selectedSchema={{
          name: "Save Image",
          type_name: "imaging.save_image",
          base_category: "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          direction: "output",
          config_schema: { properties: {} },
          type_hierarchy: [],
          format_capabilities: [
            makeCapability({ id: "imaging.image.tiff.save", label: "TIFF" }),
            makeCapability({
              id: "imaging.image.png.save",
              extensions: [".png"],
              format_id: "png",
              label: "PNG",
            }),
          ],
        }}
      />,
    );

    expect(screen.getByText(/choose one to persist a stable capability_id/i)).toBeInTheDocument();
  });

  it("renders CodeBlock v2 core fields and emits backend config keys", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              interpreter_mode: "auto",
              working_directory: ".",
              exchange_root: "exchange",
              timeout_seconds: 30,
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.change(screen.getByDisplayValue("scripts/analyze.py"), {
      target: { value: "scripts/segment.py" },
    });
    expect(onUpdateConfig).toHaveBeenCalledWith({ script_path: "scripts/segment.py" });

    fireEvent.change(screen.getByDisplayValue("auto"), { target: { value: "existing" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ interpreter_mode: "existing" });

    // Timeout / Working directory were removed from the editor (2026-06 config
    // pass); exchange_root remains a core scalar field.
    fireEvent.change(screen.getByDisplayValue("exchange"), { target: { value: "io" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ exchange_root: "io" });
  });

  it("edits CodeBlock v2 environment variables", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              environment_variables: { OMP_NUM_THREADS: "4" },
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.change(screen.getByDisplayValue("4"), { target: { value: "8" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      environment_variables: { OMP_NUM_THREADS: "8" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      environment_variables: { OMP_NUM_THREADS: "4", VAR_2: "" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Remove environment variable OMP_NUM_THREADS" }),
    );
    expect(onUpdateConfig).toHaveBeenCalledWith({ environment_variables: {} });
  });

  it("keeps CodeBlock environment variables when a rename collides with another key", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              environment_variables: { EXISTING: "1", THREADS: "4" },
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.change(screen.getByDisplayValue("THREADS"), { target: { value: "EXISTING" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      environment_variables: { EXISTING: "1", THREADS: "4" },
    });
  });

  it("edits and removes CodeBlock v2 declared input rows", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              inputs: [
                {
                  name: "image",
                  direction: "input",
                  data_type: "Image",
                  extension: ".tif",
                  capability_id: "imaging.image.tiff.save",
                  required: true,
                  exchange_folder: "inputs/image/",
                },
              ],
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.change(screen.getByDisplayValue("image"), { target: { value: "raw_image" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      inputs: [
        {
          name: "raw_image",
          direction: "input",
          data_type: "Image",
          extension: ".tif",
          capability_id: "imaging.image.tiff.save",
          required: true,
          exchange_folder: "inputs/raw_image/",
        },
      ],
      // Hotfix 2026-05-23 — mirror the v2 list into the variadic-port list
      // the canvas reads from, so the BottomPanel editor and the canvas stay
      // in sync without a separate user action.
      input_ports: [{ name: "raw_image", types: ["Image"] }],
    });

    fireEvent.change(screen.getByDisplayValue("Image"), { target: { value: "DataFrame" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      inputs: [
        {
          name: "image",
          direction: "input",
          data_type: "DataFrame",
          extension: ".tif",
          // #1366 parity: changing the data type clears the pinned capability.
          capability_id: null,
          required: true,
          exchange_folder: "inputs/image/",
        },
      ],
      input_ports: [{ name: "image", types: ["DataFrame"] }],
    });

    fireEvent.click(screen.getByLabelText("Required"));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      inputs: [
        {
          name: "image",
          direction: "input",
          data_type: "Image",
          extension: ".tif",
          capability_id: "imaging.image.tiff.save",
          required: false,
          exchange_folder: "inputs/image/",
        },
      ],
      input_ports: [{ name: "image", types: ["Image"] }],
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove input image" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({ inputs: [], input_ports: [] });
  });

  it("adds and edits CodeBlock v2 declared output rows", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              outputs: [
                {
                  name: "table",
                  direction: "output",
                  data_type: "DataFrame",
                  extension: ".csv",
                  capability_id: "core.dataframe.csv.load",
                  required: true,
                  exchange_folder: "outputs/table/",
                },
              ],
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add output" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      outputs: [
        {
          name: "table",
          direction: "output",
          data_type: "DataFrame",
          extension: ".csv",
          capability_id: "core.dataframe.csv.load",
          required: true,
          exchange_folder: "outputs/table/",
        },
        {
          name: "output_2",
          direction: "output",
          data_type: "DataObject",
          extension: ".txt",
          capability_id: null,
          required: true,
          exchange_folder: "outputs/output_2/",
        },
      ],
      output_ports: [
        { name: "table", types: ["DataFrame"] },
        { name: "output_2", types: ["DataObject"] },
      ],
    });

    fireEvent.change(screen.getByDisplayValue(".csv"), { target: { value: ".tsv" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      outputs: [
        {
          name: "table",
          direction: "output",
          data_type: "DataFrame",
          extension: ".tsv",
          // #1366 parity: changing the extension clears the pinned capability.
          capability_id: null,
          required: true,
          exchange_folder: "outputs/table/",
        },
      ],
      output_ports: [{ name: "table", types: ["DataFrame"] }],
    });

    fireEvent.change(screen.getByDisplayValue("outputs/table/"), {
      target: { value: "outputs/results/" },
    });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      outputs: [
        {
          name: "table",
          direction: "output",
          data_type: "DataFrame",
          extension: ".csv",
          capability_id: "core.dataframe.csv.load",
          required: true,
          exchange_folder: "outputs/results/",
        },
      ],
      output_ports: [{ name: "table", types: ["DataFrame"] }],
    });
  });

  // --- #1373: native file-browser fallback regression coverage ---

  // Shared helper: render BottomPanel with a single-field browser schema.
  function renderBrowser(
    widget: "file_browser" | "directory_browser",
    initialPath: string,
    onUpdateConfig = vi.fn(),
  ) {
    const isDir = widget === "directory_browser";
    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: isDir ? "proc-1" : "load-1",
          block_type: isDir ? "process_block" : "load_data",
          config: { params: isDir ? { output_dir: initialPath } : { path: initialPath } },
        }}
        selectedSchema={{
          name: isDir ? "Process Block" : "Load",
          type_name: isDir ? "process_block" : "load_data",
          base_category: isDir ? "process" : "io",
          subcategory: "",
          description: "",
          version: "0.1.0",
          input_ports: [],
          output_ports: [],
          config_schema: {
            properties: {
              [isDir ? "output_dir" : "path"]: {
                type: "string",
                title: isDir ? "Output directory" : "Path",
                ui_priority: 0,
                ui_widget: widget,
              },
            },
          },
          type_hierarchy: [],
        }}
      />,
    );
    return onUpdateConfig;
  }

  it("config Browse button succeeds via native dialog (file_browser)", async () => {
    // #1373: BottomPanel with a file_browser field must use openNativeDialog first.
    apiMocks.openNativeDialog.mockResolvedValueOnce({ paths: ["/projects/data/sample.tif"] });
    const onUpdateConfig = renderBrowser("file_browser", "/projects/data/old.tif");
    fireEvent.click(screen.getByTitle("Browse filesystem"));
    await waitFor(() =>
      expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", "/projects/data"),
    );
    await waitFor(() =>
      expect(onUpdateConfig).toHaveBeenCalledWith({ path: "/projects/data/sample.tif" }),
    );
    expect(apiMocks.browseFilesystem).not.toHaveBeenCalled();
  });

  it("config Browse button falls back to in-app modal on native dialog failure (file_browser)", async () => {
    // #1373: HTTP 500 from openNativeDialog triggers the FileBrowserModal fallback.
    const { ApiError } = await import("../lib/api");
    apiMocks.openNativeDialog.mockRejectedValueOnce(new ApiError("Not available", 500));
    apiMocks.browseFilesystem.mockResolvedValueOnce({ path: "/projects/data", entries: [] });
    renderBrowser("file_browser", "");
    fireEvent.click(screen.getByTitle("Browse filesystem"));
    expect(await screen.findByText("Select File")).toBeInTheDocument();
    expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", undefined);
  });

  it("config Browse button falls back to in-app modal on native dialog failure (directory_browser)", async () => {
    // #1373: directory_browser mode also falls back; uses process_block to avoid
    // CodeBlockConfigEditor which bypasses the generic browse button.
    const { ApiError } = await import("../lib/api");
    apiMocks.openNativeDialog.mockRejectedValueOnce(new ApiError("Not supported", 500));
    apiMocks.browseFilesystem.mockResolvedValueOnce({ path: "/projects", entries: [] });
    renderBrowser("directory_browser", "");
    fireEvent.click(screen.getByTitle("Browse filesystem"));
    expect(await screen.findByText("Select Directory")).toBeInTheDocument();
    expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("directory", undefined);
  });

  it("config Browse button does not update config when user cancels native dialog", async () => {
    // #1373: user-cancel (empty paths list) must not call onUpdateConfig.
    apiMocks.openNativeDialog.mockResolvedValueOnce({ paths: [] });
    const onUpdateConfig = renderBrowser("file_browser", "/old/path.tif");
    fireEvent.click(screen.getByTitle("Browse filesystem"));
    await waitFor(() => expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file", "/old"));
    expect(onUpdateConfig).not.toHaveBeenCalled();
  });

  it("adds CodeBlock v2 output rows with non-colliding default names", () => {
    const onUpdateConfig = vi.fn();

    render(
      <BottomPanel
        activeTab="config"
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "code-1",
          block_type: "code_block",
          config: {
            params: {
              script_path: "scripts/analyze.py",
              outputs: [
                {
                  name: "output_2",
                  direction: "output",
                  data_type: "DataObject",
                  extension: ".txt",
                  capability_id: null,
                  required: true,
                  exchange_folder: "outputs/output_2/",
                },
              ],
            },
          },
        }}
        selectedSchema={codeBlockSchema}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add output" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      outputs: [
        {
          name: "output_2",
          direction: "output",
          data_type: "DataObject",
          extension: ".txt",
          capability_id: null,
          required: true,
          exchange_folder: "outputs/output_2/",
        },
        {
          name: "output_3",
          direction: "output",
          data_type: "DataObject",
          extension: ".txt",
          capability_id: null,
          required: true,
          exchange_folder: "outputs/output_3/",
        },
      ],
      output_ports: [
        { name: "output_2", types: ["DataObject"] },
        { name: "output_3", types: ["DataObject"] },
      ],
    });
  });
});
