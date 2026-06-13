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
 */
import { describe, expect, it, vi } from "vitest";

import type { PlotRunResponse } from "../../../types/api";
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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
    vi.stubGlobal("fetch", fetchMock);

    const out = await dataApi.runPlotJob({ plot_id: "p1" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/plots/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ plot_id: "p1" });
    expect(out).toEqual(body);

    // The run response feeds straight into the production trigger.
    const target = plotTargetFromRunResponse(out);
    expect(target?.kind).toBe("plot_artifact");
    expect(target?.ref).toBe("data-abc123");

    vi.unstubAllGlobals();
  });
});

describe("dataApi plot list + preview resource save", () => {
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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
    vi.stubGlobal("fetch", fetchMock);

    const out = await dataApi.listPlots({ workflowId: "main", nodeId: "node_a" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/plots?workflow_id=main&node_id=node_a");
    expect(out).toEqual(body);
    vi.unstubAllGlobals();
  });

  it("POSTs preview resource saves to the selected destination path", async () => {
    const body = {
      path: "C:/Users/test/plot.svg",
      filename: "plot.svg",
      size_bytes: 7,
      mime_type: "image/svg+xml",
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
    vi.stubGlobal("fetch", fetchMock);

    const out = await dataApi.savePreviewResource("pv-1", "export", {
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/previews/sessions/pv-1/resources/export/save");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });
    expect(out).toEqual(body);
    vi.unstubAllGlobals();
  });
});
