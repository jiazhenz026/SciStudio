import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";
import { useAppStore } from "../../store";
import type { BlockSummary, PlotListItem, PlotTargetItem } from "../../types/api";

const listPlotTargets = vi.fn();
const createPlot = vi.fn();
const relinkPlot = vi.fn();

// Partial mock: the real store (imported below) pulls other exports from this
// module at creation time, so keep them and only stub the three api methods.
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listPlotTargets: (...args: unknown[]) => listPlotTargets(...args),
      createPlot: (...args: unknown[]) => createPlot(...args),
      relinkPlot: (...args: unknown[]) => relinkPlot(...args),
    },
  };
});

import { PlotTargetPicker } from "./PlotTargetPicker";

function target(overrides: Partial<PlotTargetItem>): PlotTargetItem {
  return {
    target_id: "t-a",
    workflow_path: "workflows/main.yaml",
    workflow_id: "main",
    node_id: "demo_block-1",
    node_label: "",
    block_type: "demo_block",
    output_port: "out",
    output_type: "Spectrum",
    is_collection: false,
    latest_run_id: "run-1",
    latest_output_available: true,
    diagnostics: [],
    ...overrides,
  };
}

function plot(overrides: Partial<PlotListItem>): PlotListItem {
  return {
    plot_id: "qc",
    title: "QC",
    workflow_id: "main",
    node_id: "demo_block-1",
    output_port: "out",
    display_label: "Demo Block / out",
    language: "python",
    preferred_format: "png",
    manifest_path: "plots/qc/plot.yaml",
    script_path: "plots/qc/render.py",
    ...overrides,
  } as PlotListItem;
}

beforeEach(() => {
  listPlotTargets.mockReset();
  createPlot.mockReset();
  relinkPlot.mockReset();
  useAppStore.setState({
    blocks: [{ name: "Demo Block", type_name: "demo_block" } as BlockSummary],
    blockSchemas: {},
    highlightedNodeId: null,
  });
});

afterEach(cleanup);

describe("PlotTargetPicker", () => {
  it("shows readable rows (no node_id) and highlights the block on hover", async () => {
    listPlotTargets.mockResolvedValue({ count: 1, targets: [target({ target_id: "t1" })] });

    render(
      <PlotTargetPicker
        defaultNodeId={null}
        mode="new"
        onClose={vi.fn()}
        onCreated={vi.fn()}
        workflowId="main"
      />,
    );

    const row = await screen.findByRole("option", { name: /Demo Block · out/ });
    expect(row.textContent).not.toContain("demo_block-1");
    // Default selection surfaces the block immediately.
    await waitFor(() => expect(useAppStore.getState().highlightedNodeId).toBe("demo_block-1"));

    fireEvent.mouseEnter(row);
    expect(useAppStore.getState().highlightedNodeId).toBe("demo_block-1");
  });

  it("creates a plot bound to the chosen target", async () => {
    const onCreated = vi.fn();
    const onClose = vi.fn();
    listPlotTargets.mockResolvedValue({ count: 1, targets: [target({ target_id: "t1" })] });
    createPlot.mockResolvedValue({ script_path: "plots/My_Plot/render.py", warnings: [] });

    render(
      <PlotTargetPicker
        defaultNodeId="demo_block-1"
        mode="new"
        onClose={onClose}
        onCreated={onCreated}
        workflowId="main"
      />,
    );

    await screen.findByRole("option", { name: /Demo Block · out/ });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My Plot" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(createPlot).toHaveBeenCalledWith({
        plot_id: "My_Plot",
        target_id: "t1",
        title: "My Plot",
        language: "python",
      }),
    );
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ script_path: "plots/My_Plot/render.py" }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("relinks an existing plot to the chosen target", async () => {
    const onRelinked = vi.fn();
    const onClose = vi.fn();
    listPlotTargets.mockResolvedValue({
      count: 2,
      targets: [
        target({ target_id: "t1", node_id: "demo_block-1", output_port: "out" }),
        target({ target_id: "t2", node_id: "demo_block-1", output_port: "extra" }),
      ],
    });
    relinkPlot.mockResolvedValue({ valid: true, errors: [] });

    render(
      <PlotTargetPicker
        mode="relink"
        onClose={onClose}
        onRelinked={onRelinked}
        plot={plot({ output_port: "extra" })}
        workflowId="main"
      />,
    );

    await screen.findByRole("option", { name: /Demo Block · extra/ });
    fireEvent.click(screen.getByRole("button", { name: "Relink" }));

    await waitFor(() => expect(relinkPlot).toHaveBeenCalledWith("qc", { target_id: "t2" }));
    expect(onRelinked).toHaveBeenCalledWith(expect.objectContaining({ valid: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
