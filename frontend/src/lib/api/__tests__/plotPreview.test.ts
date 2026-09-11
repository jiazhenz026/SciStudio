/**
 * ADR-048 SPEC 2 / #1606 — production trigger that opens a plot preview.
 *
 * Guards the frontend half of the dead-wire fix: after `runPlotJob` registers
 * the produced artifact and returns its catalog `data_ref`, the GUI builds a
 * `plot_artifact` {@link PreviewTarget} from the run response and hands it to
 * `PreviewHost`, which opens a routed preview session that renders the figure
 * through the core PlotPreviewer. A successful run MUST yield a routable target;
 * a failed/empty run MUST yield `null` so the UI shows the failure instead of an
 * empty preview.
 *
 * The client round trips run against `mockBackend()`, which checks every
 * request and response body against the backend contract (#2297).
 */
import { afterEach, describe, expect, it } from "vitest";

import type { PlotRunResponse } from "../../../types/api";
import { mockBackend, reply, type MockBackend } from "../../../__tests__/contract/mockBackend";
import { dataApi, plotTargetFromRunResponse } from "../data";

function successResponse(overrides: Partial<PlotRunResponse> = {}): PlotRunResponse {
  return {
    status: "succeeded",
    data_ref: "data-abc123",
    recorded_type: "PlotArtifact",
    type_chain: ["DataObject", "PlotArtifact"],
    cache_key: "plot_deadbeef",
    artifact_paths: ["/proj/.scistudio/previews/main/node_a/measurements/p1/current.svg"],
    source: { workflow_id: "main", node_id: "node_a", output_port: "measurements" },
    warnings: [],
    errors: [],
    ...overrides,
  };
}

const PLOT_TARGET = {
  target_id: "tgt_1",
  workflow_path: "workflows/main.yaml",
  workflow_id: "main",
  node_id: "node_a",
  node_label: "Load",
  block_type: "io.load",
  output_port: "data",
  output_type: "DataFrame",
  is_collection: false,
  latest_run_id: null,
  latest_output_available: false,
  diagnostics: [],
};

let backend: MockBackend | undefined;

afterEach(() => {
  backend?.restore();
  backend = undefined;
});

describe("plotTargetFromRunResponse (#1606 production trigger)", () => {
  it("builds a routable plot_artifact target from a successful run", () => {
    const target = plotTargetFromRunResponse(successResponse());
    expect(target).not.toBeNull();
    expect(target).toMatchObject({
      kind: "plot_artifact",
      ref: "data-abc123",
      recorded_type: "PlotArtifact",
      type_chain: ["DataObject", "PlotArtifact"],
      source: { node_id: "node_a", output_port: "measurements" },
    });
  });

  it("falls back to the canonical plot type chain when the backend omits it", () => {
    const target = plotTargetFromRunResponse(
      successResponse({ recorded_type: "", type_chain: [] }),
    );
    expect(target?.recorded_type).toBe("PlotArtifact");
    expect(target?.type_chain).toEqual(["DataObject", "PlotArtifact"]);
  });

  it("returns null for a failed run so no empty preview opens", () => {
    expect(
      plotTargetFromRunResponse(
        successResponse({ status: "failed", data_ref: null, errors: ["boom"] }),
      ),
    ).toBeNull();
  });

  it("returns null when a succeeded run has no data_ref", () => {
    expect(plotTargetFromRunResponse(successResponse({ data_ref: null }))).toBeNull();
  });
});

describe("dataApi.runPlotJob (#1606 run route)", () => {
  it("POSTs the plot run request to /api/plots/run and returns the response", async () => {
    const body = successResponse();
    backend = mockBackend({ "POST /api/plots/run": body });

    const out = await dataApi.runPlotJob({ plot_id: "p1" });

    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]?.url).toBe("/api/plots/run");
    expect(backend.calls[0]?.body).toEqual({ plot_id: "p1" });
    expect(out).toEqual(body);

    // The run response feeds straight into the production trigger.
    const target = plotTargetFromRunResponse(out);
    expect(target?.kind).toBe("plot_artifact");
    expect(target?.ref).toBe("data-abc123");
  });
});

describe("dataApi plot list + preview resource save", () => {
  it("GETs /api/plots/targets with the active workflow filter", async () => {
    const body = { targets: [PLOT_TARGET], count: 1 };
    backend = mockBackend({ "GET /api/plots/targets": body });

    const out = await dataApi.listPlotTargets({ workflowId: "main" });

    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]?.url).toBe("/api/plots/targets?workflow_id=main");
    expect(out).toEqual(body);
  });

  it("POSTs a plot scaffold request to /api/plots", async () => {
    const body = {
      plot_id: "my_plot",
      manifest_path: "plots/my_plot/plot.yaml",
      script_path: "plots/my_plot/render.py",
      bytes_written: 100,
      warnings: [],
      target: PLOT_TARGET,
    };
    backend = mockBackend({ "POST /api/plots": body });

    const out = await dataApi.createPlot({
      plot_id: "my_plot",
      target_id: "tgt_1",
      title: "My Plot",
      language: "python",
    });

    expect(backend.calls[0]?.method).toBe("POST");
    expect(backend.calls[0]?.url).toBe("/api/plots");
    expect(backend.calls[0]?.body).toEqual({
      plot_id: "my_plot",
      target_id: "tgt_1",
      title: "My Plot",
      language: "python",
    });
    expect(out).toEqual(body);
  });

  it("DELETEs a plot by its encoded id", async () => {
    backend = mockBackend({ "DELETE /api/plots/{plot_id}": reply(204) });

    await dataApi.deletePlot("plot one");

    expect(backend.calls[0]?.method).toBe("DELETE");
    expect(backend.calls[0]?.url).toBe("/api/plots/plot%20one");
  });

  it("GETs /api/plots with block filters", async () => {
    const body = {
      plots: [
        {
          plot_id: "p1",
          title: "P1",
          workflow_id: "main",
          node_id: "node_a",
          output_port: "measurements",
          display_label: "Seg / measurements",
          language: "python",
          preferred_format: "svg",
          manifest_path: "plots/p1/plot.yaml",
          script_path: "plots/p1/render.py",
        },
      ],
      count: 1,
      warnings: [],
    };
    backend = mockBackend({ "GET /api/plots": body });

    const out = await dataApi.listPlots({ workflowId: "main", nodeId: "node_a" });

    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]?.url).toBe("/api/plots?workflow_id=main&node_id=node_a");
    expect(out).toEqual(body);
  });

  it("POSTs preview resource saves to the selected destination path", async () => {
    const body = {
      path: "C:/Users/test/plot.svg",
      filename: "plot.svg",
      size_bytes: 7,
      mime_type: "image/svg+xml",
    };
    backend = mockBackend({
      "POST /api/previews/sessions/{session_id}/resources/{resource_id}/save": body,
    });

    const out = await dataApi.savePreviewResource("pv-1", "export", {
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });

    expect(backend.calls[0]?.method).toBe("POST");
    expect(backend.calls[0]?.url).toBe("/api/previews/sessions/pv-1/resources/export/save");
    expect(backend.calls[0]?.body).toEqual({
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });
    expect(out).toEqual(body);
  });
});
