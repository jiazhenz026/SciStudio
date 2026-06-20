import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlotListItem, PlotRelinkResponse, PlotTargetItem } from "../types/api";

const listPlotTargets = vi.fn();
const relinkPlot = vi.fn();

vi.mock("../lib/api", () => ({
  api: {
    listPlotTargets: (...args: unknown[]) => listPlotTargets(...args),
    relinkPlot: (...args: unknown[]) => relinkPlot(...args),
  },
}));

import { RelinkPlotDialog } from "./RelinkPlotDialog";

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

function plot(overrides: Partial<PlotListItem>): PlotListItem {
  return {
    plot_id: "p1",
    title: "QC Plot",
    workflow_id: "main",
    node_id: "node_old",
    output_port: "out",
    display_label: "Old Node",
    language: "python",
    preferred_format: "svg",
    manifest_path: "plots/p1/plot.yaml",
    script_path: "plots/p1/render.py",
    ...overrides,
  };
}

function relinkResponse(overrides: Partial<PlotRelinkResponse>): PlotRelinkResponse {
  return {
    plot_id: "p1",
    manifest_path: "plots/p1/plot.yaml",
    target: target({ target_id: "target-b", node_id: "node_b" }),
    valid: true,
    errors: [],
    warnings: [],
    ...overrides,
  };
}

beforeEach(() => {
  listPlotTargets.mockReset();
  relinkPlot.mockReset();
});

afterEach(cleanup);

describe("RelinkPlotDialog", () => {
  it("loads targets, defaults to the current binding, and relinks to a chosen target", async () => {
    const onClose = vi.fn();
    const onRelinked = vi.fn();
    listPlotTargets.mockResolvedValue({
      count: 2,
      targets: [
        target({ target_id: "target-old", node_id: "node_old", node_label: "Old Node" }),
        target({ target_id: "target-b", node_id: "node_b", node_label: "New Node" }),
      ],
    });
    const result = relinkResponse({});
    relinkPlot.mockResolvedValue(result);

    render(
      <RelinkPlotDialog
        open
        plot={plot({ node_id: "node_old", output_port: "out" })}
        workflowId="main"
        onClose={onClose}
        onRelinked={onRelinked}
      />,
    );

    await waitFor(() =>
      expect(listPlotTargets).toHaveBeenCalledWith({
        workflowId: "main",
        includeUnavailable: true,
      }),
    );
    // Defaults to the plot's current still-resolving binding.
    await waitFor(() => expect(screen.getByLabelText("Bind to")).toHaveValue("target-old"));

    fireEvent.change(screen.getByLabelText("Bind to"), { target: { value: "target-b" } });
    fireEvent.click(screen.getByText("Relink"));

    await waitFor(() => expect(relinkPlot).toHaveBeenCalledWith("p1", { target_id: "target-b" }));
    expect(onRelinked).toHaveBeenCalledWith(result);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("surfaces a relink failure and keeps the dialog open", async () => {
    const onClose = vi.fn();
    const onRelinked = vi.fn();
    listPlotTargets.mockResolvedValue({
      count: 1,
      targets: [target({ target_id: "target-b", node_id: "node_b" })],
    });
    relinkPlot.mockRejectedValue(new Error("Unknown plot target."));

    render(
      <RelinkPlotDialog
        open
        plot={plot({})}
        workflowId="main"
        onClose={onClose}
        onRelinked={onRelinked}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText("Bind to")).toHaveValue("target-b"));
    fireEvent.click(screen.getByText("Relink"));

    await waitFor(() => expect(screen.getByText("Unknown plot target.")).toBeInTheDocument());
    expect(onRelinked).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not load targets while closed", () => {
    render(
      <RelinkPlotDialog
        open={false}
        plot={plot({})}
        workflowId="main"
        onClose={vi.fn()}
        onRelinked={vi.fn()}
      />,
    );
    expect(listPlotTargets).not.toHaveBeenCalled();
    expect(screen.queryByText("Relink data source")).not.toBeInTheDocument();
  });
});
