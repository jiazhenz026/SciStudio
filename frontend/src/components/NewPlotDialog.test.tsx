import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlotTargetItem } from "../types/api";

const listPlotTargets = vi.fn();
const createPlot = vi.fn();

vi.mock("../lib/api", () => ({
  api: {
    listPlotTargets: (...args: unknown[]) => listPlotTargets(...args),
    createPlot: (...args: unknown[]) => createPlot(...args),
  },
}));

import { NewPlotDialog } from "./NewPlotDialog";

function target(overrides: Partial<PlotTargetItem>): PlotTargetItem {
  return {
    target_id: "target-a",
    workflow_path: "workflows/main.yaml",
    workflow_id: "main",
    node_id: "node_a",
    node_label: "Node A",
    block_type: "demo.block",
    output_port: "out",
    output_type: "DataFrame",
    is_collection: false,
    latest_run_id: "run-1",
    latest_output_available: true,
    diagnostics: [],
    ...overrides,
  };
}

beforeEach(() => {
  listPlotTargets.mockReset();
  createPlot.mockReset();
});

afterEach(cleanup);

describe("NewPlotDialog", () => {
  it("defaults to the selected node target and can create an R plot", async () => {
    const saveWorkflow = vi.fn(async () => undefined);
    const onClose = vi.fn();
    const onCreated = vi.fn();
    const selectedTarget = target({
      target_id: "target-b",
      node_id: "node_b",
      node_label: "Selected Node",
      output_port: "measurements",
    });
    listPlotTargets.mockResolvedValue({
      count: 2,
      targets: [
        target({ target_id: "target-a", node_id: "node_a", node_label: "Other Node" }),
        selectedTarget,
      ],
    });
    createPlot.mockResolvedValue({
      plot_id: "QC_Plot",
      manifest_path: "plots/QC_Plot/plot.yaml",
      script_path: "plots/QC_Plot/render.R",
      bytes_written: 100,
      warnings: [],
      target: selectedTarget,
    });

    render(
      <NewPlotDialog
        onClose={onClose}
        onCreated={onCreated}
        open
        saveWorkflow={saveWorkflow}
        selectedNodeId="node_b"
        workflowId="main"
      />,
    );

    await waitFor(() =>
      expect(listPlotTargets).toHaveBeenCalledWith({
        workflowId: "main",
        includeUnavailable: true,
      }),
    );
    expect(saveWorkflow).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Bind to")).toHaveValue("target-b");

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "QC Plot" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "r" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() =>
      expect(createPlot).toHaveBeenCalledWith({
        plot_id: "QC_Plot",
        target_id: "target-b",
        title: "QC Plot",
        language: "r",
      }),
    );
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ script_path: "plots/QC_Plot/render.R" }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not reset fields when the parent rerenders with a new save callback", async () => {
    const firstSaveWorkflow = vi.fn(async () => undefined);
    const secondSaveWorkflow = vi.fn(async () => undefined);
    const selectedTarget = target({ target_id: "target-b", node_id: "node_b" });
    listPlotTargets.mockResolvedValue({ count: 1, targets: [selectedTarget] });

    const { rerender } = render(
      <NewPlotDialog
        onClose={vi.fn()}
        onCreated={vi.fn()}
        open
        saveWorkflow={firstSaveWorkflow}
        selectedNodeId="node_b"
        workflowId="main"
      />,
    );

    await waitFor(() => expect(screen.getByLabelText("Bind to")).toHaveValue("target-b"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "edited plot" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "r" } });

    rerender(
      <NewPlotDialog
        onClose={vi.fn()}
        onCreated={vi.fn()}
        open
        saveWorkflow={secondSaveWorkflow}
        selectedNodeId="node_b"
        workflowId="main"
      />,
    );

    expect(screen.getByLabelText("Name")).toHaveValue("edited plot");
    expect(screen.getByLabelText("Language")).toHaveValue("r");
    expect(screen.getByLabelText("Bind to")).toHaveValue("target-b");
    expect(listPlotTargets).toHaveBeenCalledTimes(1);
    expect(secondSaveWorkflow).not.toHaveBeenCalled();
  });
});
