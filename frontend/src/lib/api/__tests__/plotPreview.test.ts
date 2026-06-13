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
