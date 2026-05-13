import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomPanel } from "./BottomPanel";

vi.mock("../lib/api", () => ({
  api: {},
}));

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
        blockErrors={{}}
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
  // badge must vanish.
  it("renders an unread badge next to Logs/Problems when counts > 0 and tab is hidden", () => {
    render(
      <BottomPanel
        activeTab="ai"
        blockErrors={{}}
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={null}
        unreadLogsCount={3}
        unreadProblemsCount={1}
      />,
    );

    expect(screen.getByTestId("unread-badge-logs")).toHaveTextContent("3");
    expect(screen.getByTestId("unread-badge-problems")).toHaveTextContent("1");
  });

  it("does not render the unread badge for the currently active tab", () => {
    render(
      <BottomPanel
        activeTab="logs"
        blockErrors={{}}
        logEntries={[]}
        onTabChange={() => {}}
        onUpdateConfig={() => {}}
        selectedNode={null}
        unreadLogsCount={5}
        unreadProblemsCount={0}
      />,
    );

    // Logs is active -> no badge on logs.
    expect(screen.queryByTestId("unread-badge-logs")).toBeNull();
    // Problems count is zero -> no badge there either.
    expect(screen.queryByTestId("unread-badge-problems")).toBeNull();
  });

  it("caps the unread badge at 99+", () => {
    render(
      <BottomPanel
        activeTab="ai"
        blockErrors={{}}
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
        blockErrors={{}}
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
});
