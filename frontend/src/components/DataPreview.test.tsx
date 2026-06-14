import { render, waitFor, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlotRunResponse, PreviewEnvelope } from "../types/api";

// Mock only PreviewHost's session methods plus the plot-run trigger; keep every
// other lib/api export intact (the Zustand store imports named helpers at init).
const createPreviewSession = vi.fn();
const patchPreviewSession = vi.fn();
const getPreviewSession = vi.fn();
const runPlotJob = vi.fn();
const listPlots = vi.fn();
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const actualApi = (actual.api ?? {}) as Record<string, unknown>;
  return {
    ...actual,
    api: {
      ...actualApi,
      createPreviewSession: (...a: unknown[]) => createPreviewSession(...a),
      patchPreviewSession: (...a: unknown[]) => patchPreviewSession(...a),
      getPreviewSession: (...a: unknown[]) => getPreviewSession(...a),
      runPlotJob: (...a: unknown[]) => runPlotJob(...a),
      listPlots: (...a: unknown[]) => listPlots(...a),
    },
  };
});

import { useAppStore } from "../store";

import { DataPreview } from "./DataPreview";

function textEnvelope(ref: string, text: string): PreviewEnvelope {
  return {
    session_id: `session-${ref}`,
    previewer_id: "core.text.basic",
    target: { kind: "data_ref", ref },
    kind: "text",
    payload: { text },
    resources: [],
    metadata: { complete: true },
    diagnostics: [],
    error: null,
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
  createPreviewSession.mockReset();
  createPreviewSession.mockImplementation(async (target: { ref: string }) =>
    textEnvelope(target.ref, `preview of ${target.ref}`),
  );
  runPlotJob.mockReset();
  listPlots.mockReset();
  listPlots.mockResolvedValue({ plots: [], count: 0, warnings: [] });
  // Each test owns a clean envelope cache (the store is a global singleton).
  useAppStore.getState().clearPreviewEnvelopeCache();
});

afterEach(() => {
  cleanup();
});

describe("DataPreview", () => {
  it("prompts to pick a block when nothing is selected", () => {
    render(<DataPreview blockOutputs={{}} selectedNodeId={null} selectedNodeLabel="" />);
    expect(screen.getByText(/Pick a block/i)).toBeInTheDocument();
  });

  it("shows an empty state when the selected block has no previewable outputs", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": {} }}
        selectedNodeId="node-1"
        selectedNodeLabel="Empty Block"
      />,
    );
    expect(screen.queryByText(/no previewable outputs/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Nothing to preview yet")).toHaveLength(1);
  });

  it("mounts the routed PreviewHost for the active output ref (#1592)", async () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "data-123" } } }}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    // The routed session is created for the first output ref.
    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "data_ref", ref: "data-123" }),
        expect.anything(),
      );
    });
    // The PreviewHost container renders once the envelope resolves.
    await waitFor(() => {
      expect(screen.getByTestId("preview-host")).toBeInTheDocument();
    });
  });

  it("switches the routed session when a different output pill is picked", async () => {
    render(
      <DataPreview
        blockOutputs={{
          "load-1": {
            output_a: { data_ref: "data-a" },
            output_b: { data_ref: "data-b" },
          },
        }}
        selectedNodeId="load-1"
        selectedNodeLabel="Load Image"
      />,
    );

    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({ ref: "data-a" }),
        expect.anything(),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "data-b" }));

    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({ ref: "data-b" }),
        expect.anything(),
      );
    });
  });

  it("opens collection outputs as collection-level sessions", async () => {
    render(
      <DataPreview
        blockOutputs={{
          "load-1": {
            images: {
              kind: "collection",
              item_type: "DataFrame",
              items: [{ data_ref: "data-a", type_name: "DataFrame" }, { data_ref: "data-b" }],
            },
          },
        }}
        selectedNodeId="load-1"
        selectedNodeLabel="Load Table"
      />,
    );

    expect(await screen.findByRole("button", { name: "images (2)" })).toBeInTheDocument();
    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "collection_ref",
          ref: "collection:images",
          recorded_type: "DataFrame",
          collection_item_type: "DataFrame",
          source: expect.objectContaining({ node_id: "load-1", output_port: "images" }),
        }),
        expect.objectContaining({
          _collection_count: 2,
          _collection_item_type: "DataFrame",
          _collection_items: [
            { data_ref: "data-a", type_name: "DataFrame" },
            { data_ref: "data-b" },
          ],
        }),
      );
    });
  });

  it("runs a plot job and mounts PreviewHost for the returned plot artifact (#1623)", async () => {
    listPlots.mockResolvedValue({
      plots: [
        {
          plot_id: "p1",
          title: "P1",
          workflow_id: "main",
          node_id: "node-1",
          output_port: "output",
          display_label: "Process Block / output",
          language: "python",
          preferred_format: "svg",
          manifest_path: "plots/p1/plot.yaml",
          script_path: "plots/p1/render.py",
        },
      ],
      count: 1,
      warnings: [],
    });
    runPlotJob.mockResolvedValue(plotRunResponse());

    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "data-123" } } }}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "data_ref", ref: "data-123" }),
        expect.anything(),
      );
    });

    fireEvent.click(await screen.findByRole("button", { name: "Run plot P1" }));

    await waitFor(() => expect(runPlotJob).toHaveBeenCalledWith({ plot_id: "p1" }));
    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "plot_artifact",
          ref: "data-plot-1",
          recorded_type: "PlotArtifact",
          type_chain: ["DataObject", "PlotArtifact"],
          source: { workflow_id: "main", node_id: "node-1", output_port: "output" },
        }),
        expect.anything(),
      );
    });
    expect(screen.getByRole("button", { name: "Plot artifact" })).toBeInTheDocument();
  });

  // #898 - pill labels show source filename (independent of the renderer).
  it("pill label shows source filename when framework.source is set (#898)", () => {
    render(
      <DataPreview
        blockOutputs={{
          "load-1": {
            image_a: {
              data_ref: "data-abcdef",
              metadata: { framework: { source: "C:/data/beads.tif" } },
            },
            image_b: {
              data_ref: "data-123456",
              metadata: { meta: { source_file: "/home/u/sample_002.tif" } },
            },
            image_c: { data_ref: "data-xyz789", metadata: { framework: { source: "" } } },
          },
        }}
        selectedNodeId="load-1"
        selectedNodeLabel="Load Image"
      />,
    );

    expect(screen.getByRole("button", { name: "beads.tif" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "sample_002.tif" })).toBeInTheDocument();
    // Fallback when no metadata source: truncated ref.
    expect(screen.getByRole("button", { name: "data-xyz78" })).toBeInTheDocument();
  });
});
