// #2220 — the Browse button's pending state lives in its own file because
// ConfigPanel.test.tsx is at the repository's 750-line ceiling.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigPanel } from "./ConfigPanel";

const apiMocks = vi.hoisted(() => ({
  browseFilesystem: vi.fn(),
  openNativeDialog: vi.fn(),
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
  // ConfigPanel pulls in SubworkflowConfigEditor, whose store initializer calls
  // this at module load; the mock must export it to instantiate.
  setWorkflowWriteStartedListener: vi.fn(),
  api: {
    browseFilesystem: apiMocks.browseFilesystem,
    openNativeDialog: apiMocks.openNativeDialog,
    listBlocks: apiMocks.listBlocks,
  },
}));

describe("ConfigPanel Browse button", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.browseFilesystem.mockReset();
    apiMocks.openNativeDialog.mockReset();
  });

  it("disables the Browse button while a native dialog is already open (#2220)", async () => {
    // The dialog blocks until the user dismisses it. Until #2220 the only
    // feedback that one was open was the whole app freezing; with the freeze
    // gone the button has to say so itself, and a second click must not open a
    // competing OS panel (the backend answers those with 409).
    const onUpdateConfig = vi.fn();
    let resolveDialog: (value: { paths: string[] }) => void = () => {};
    apiMocks.openNativeDialog.mockReturnValueOnce(
      new Promise<{ paths: string[] }>((resolve) => {
        resolveDialog = resolve;
      }),
    );

    render(
      <ConfigPanel
        onUpdateConfig={onUpdateConfig}
        selectedNode={{
          id: "load-1",
          block_type: "load_data",
          config: { params: { path: "/data/old.tif" } },
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

    const browseButton = screen.getByTitle("Browse filesystem");
    fireEvent.click(browseButton);

    await waitFor(() => expect(screen.getByTitle("File dialog open")).toBeDisabled());
    fireEvent.click(screen.getByTitle("File dialog open"));
    expect(apiMocks.openNativeDialog).toHaveBeenCalledTimes(1);

    resolveDialog({ paths: ["/data/new.tif"] });

    await waitFor(() => expect(onUpdateConfig).toHaveBeenCalledWith({ path: "/data/new.tif" }));
    await waitFor(() => expect(screen.getByTitle("Browse filesystem")).not.toBeDisabled());
  });
});
