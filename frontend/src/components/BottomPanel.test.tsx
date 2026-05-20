import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomPanel } from "./BottomPanel";

vi.mock("../lib/api", () => ({
  api: {},
}));

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

    fireEvent.change(screen.getByDisplayValue("scripts/analyze.py"), { target: { value: "scripts/segment.py" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ script_path: "scripts/segment.py" });

    fireEvent.change(screen.getByDisplayValue("auto"), { target: { value: "existing" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ interpreter_mode: "existing" });

    fireEvent.change(screen.getByDisplayValue("30"), { target: { value: "60" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({ timeout_seconds: 60 });
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
    expect(onUpdateConfig).toHaveBeenCalledWith({ environment_variables: { OMP_NUM_THREADS: "8" } });

    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({
      environment_variables: { OMP_NUM_THREADS: "4", VAR_2: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove environment variable OMP_NUM_THREADS" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({ environment_variables: {} });
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
    });

    fireEvent.change(screen.getByDisplayValue("Image"), { target: { value: "DataFrame" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      inputs: [
        {
          name: "image",
          direction: "input",
          data_type: "DataFrame",
          extension: ".tif",
          capability_id: "imaging.image.tiff.save",
          required: true,
          exchange_folder: "inputs/image/",
        },
      ],
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
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove input image" }));
    expect(onUpdateConfig).toHaveBeenCalledWith({ inputs: [] });
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
    });

    fireEvent.change(screen.getByDisplayValue(".csv"), { target: { value: ".tsv" } });
    expect(onUpdateConfig).toHaveBeenCalledWith({
      outputs: [
        {
          name: "table",
          direction: "output",
          data_type: "DataFrame",
          extension: ".tsv",
          capability_id: "core.dataframe.csv.load",
          required: true,
          exchange_folder: "outputs/table/",
        },
      ],
    });

    fireEvent.change(screen.getByDisplayValue("outputs/table/"), { target: { value: "outputs/results/" } });
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
    });
  });
});
