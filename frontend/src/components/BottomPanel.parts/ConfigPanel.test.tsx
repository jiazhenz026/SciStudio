import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FormatCapabilityResponse } from "../../types/api";
import { ConfigPanel } from "./ConfigPanel";

const apiMocks = vi.hoisted(() => ({
  browseFilesystem: vi.fn(),
  openNativeDialog: vi.fn(),
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
  api: {
    browseFilesystem: apiMocks.browseFilesystem,
    openNativeDialog: apiMocks.openNativeDialog,
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
});
