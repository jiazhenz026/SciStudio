import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomPanel } from "./BottomPanel";
import type { FormatCapabilityResponse } from "../types/api";

vi.mock("../lib/api", () => ({
  api: {},
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

describe("BottomPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
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

    expect(
      screen.getByText(/choose one to persist a stable capability_id/i),
    ).toBeInTheDocument();
  });
});
