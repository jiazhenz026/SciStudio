import { render, waitFor, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlotListItem, PlotRunResponse } from "../../types/api";

// PlotsTab and the New/Relink dialogs all read named methods off the shared
// `api` object; mock those used by this surface and keep the rest intact (the
// Zustand store imports named helpers at init).
const listPlots = vi.fn();
const runPlotJob = vi.fn();
const listPlotTargets = vi.fn();
const relinkPlot = vi.fn();
const createPlot = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const actualApi = (actual.api ?? {}) as Record<string, unknown>;
  return {
    ...actual,
    api: {
      ...actualApi,
      listPlots: (...a: unknown[]) => listPlots(...a),
      runPlotJob: (...a: unknown[]) => runPlotJob(...a),
      listPlotTargets: (...a: unknown[]) => listPlotTargets(...a),
      relinkPlot: (...a: unknown[]) => relinkPlot(...a),
      createPlot: (...a: unknown[]) => createPlot(...a),
    },
  };
});

import { useAppStore } from "../../store";

import { PlotsTab } from "./PlotsTab";

function makePlot(overrides: Partial<PlotListItem> = {}): PlotListItem {
  return {
    plot_id: "p1",
    title: "My Plot",
    workflow_id: "main",
    node_id: "node-1",
    output_port: "output",
    display_label: "Process Block / output",
    language: "python",
    preferred_format: "svg",
    manifest_path: "plots/p1/plot.yaml",
    script_path: "plots/p1/render.py",
    ...overrides,
  };
}

function plotRunResponse(overrides: Partial<PlotRunResponse> = {}): PlotRunResponse {
  return {
    status: "succeeded",
    data_ref: "data-plot-1",
    recorded_type: "PlotArtifact",
    type_chain: ["DataObject", "PlotArtifact"],
    cache_key: "plot_deadbeef",
    artifact_paths: ["/project/.scistudio/previews/main/node-1/output/p1/current.svg"],
    source: { workflow_id: "main", node_id: "node-1", output_port: "output" },
    warnings: [],
    errors: [],
    ...overrides,
  };
}

beforeEach(() => {
  listPlots.mockReset();
  runPlotJob.mockReset();
  listPlotTargets.mockReset();
  relinkPlot.mockReset();
  createPlot.mockReset();
  listPlots.mockResolvedValue({ plots: [], count: 0, warnings: [] });
  listPlotTargets.mockResolvedValue({ targets: [] });
  useAppStore.setState({
    workflowId: "main",
    selectedNodeId: null,
    highlightedNodeId: null,
    plotPicker: null,
  });
  useAppStore.getState().setPlotPreviewTarget(null);
});

afterEach(() => {
  cleanup();
});

describe("PlotsTab", () => {
  it("shows the empty state when there are no plots", async () => {
    render(<PlotsTab />);
    expect(await screen.findByText(/No plots in this workflow yet/i)).toBeInTheDocument();
  });

  it("renders a plot card with name, linked target, and language", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot()], count: 1, warnings: [] });
    render(<PlotsTab />);
    expect(await screen.findByText("My Plot")).toBeInTheDocument();
    expect(screen.getByText("→ Process Block / output")).toBeInTheDocument();
    // #1713 — language badge.
    expect(screen.getByText("python")).toBeInTheDocument();
  });

  it("appends the bound port type to the auto label when there is no display_label (#1721)", async () => {
    listPlots.mockResolvedValue({
      plots: [makePlot({ display_label: "", output_type: "Spectrum" })],
      count: 1,
      warnings: [],
    });
    render(<PlotsTab />);
    expect(await screen.findByText("→ node-1 / output (Spectrum)")).toBeInTheDocument();
  });

  it("omits the type suffix when output_type is empty, e.g. a broken target (#1721)", async () => {
    listPlots.mockResolvedValue({
      plots: [makePlot({ display_label: "", output_type: "" })],
      count: 1,
      warnings: [],
    });
    render(<PlotsTab />);
    expect(await screen.findByText("→ node-1 / output")).toBeInTheDocument();
  });

  it("flags a broken plot with the needs-relink badge and banner", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot({ broken: true })], count: 1, warnings: [] });
    render(<PlotsTab />);
    expect(await screen.findByLabelText("Broken target — needs relink")).toBeInTheDocument();
    // #1713 — banner under the buttons prompts the user to relink.
    expect(screen.getByText(/Needs relink — reconnect the data source/i)).toBeInTheDocument();
  });

  it("runs a plot and publishes the result to the shared store (#1713)", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot()], count: 1, warnings: [] });
    runPlotJob.mockResolvedValue(plotRunResponse());
    render(<PlotsTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Run plot My Plot" }));

    await waitFor(() => expect(runPlotJob).toHaveBeenCalledWith({ plot_id: "p1" }));
    await waitFor(() =>
      expect(useAppStore.getState().plotPreviewTarget).toMatchObject({
        kind: "plot_artifact",
        ref: "data-plot-1",
      }),
    );
    // #1713 — run also selects the plot's linked block.
    await waitFor(() => expect(useAppStore.getState().selectedNodeId).toBe("node-1"));
  });

  it("does not select a node when running a broken plot", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot({ broken: true })], count: 1, warnings: [] });
    runPlotJob.mockResolvedValue(plotRunResponse());
    render(<PlotsTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Run plot My Plot" }));

    await waitFor(() => expect(runPlotJob).toHaveBeenCalledWith({ plot_id: "p1" }));
    expect(useAppStore.getState().selectedNodeId).toBeNull();
  });

  it("surfaces a run error without publishing a result", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot()], count: 1, warnings: [] });
    runPlotJob.mockRejectedValue(new Error("boom"));
    render(<PlotsTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Run plot My Plot" }));

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(useAppStore.getState().plotPreviewTarget).toBeNull();
  });

  it("opens the in-panel relink picker from a card (#1799)", async () => {
    listPlots.mockResolvedValue({ plots: [makePlot()], count: 1, warnings: [] });
    render(<PlotsTab />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Relink data source for plot My Plot" }),
    );
    // #1799 — the picker is an in-place content mode of this panel, not a modal.
    expect(await screen.findByText("Relink data source")).toBeInTheDocument();
    expect(useAppStore.getState().plotPicker).toEqual({ mode: "relink", plotId: "p1" });
  });

  it("opens the in-panel new-plot picker (#1799)", async () => {
    render(<PlotsTab />);
    fireEvent.click(await screen.findByRole("button", { name: /New plot/i }));
    // The picker renders inline (Name field + the bind prompt), not a modal heading.
    expect(await screen.findByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByText(/Bind to a block output/i)).toBeInTheDocument();
    expect(useAppStore.getState().plotPicker).toEqual({ mode: "new" });
  });
});
