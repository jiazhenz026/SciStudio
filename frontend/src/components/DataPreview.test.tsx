import { render, waitFor, screen, fireEvent, cleanup, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope } from "../types/api";

// Mock only PreviewHost's session methods; keep every other lib/api export
// intact (the Zustand store imports named helpers at init). #1713 — plot
// run/list moved to the Plots tab, so DataPreview no longer calls those.
const createPreviewSession = vi.fn();
const patchPreviewSession = vi.fn();
const getPreviewSession = vi.fn();
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

beforeEach(() => {
  createPreviewSession.mockReset();
  createPreviewSession.mockImplementation(async (target: { ref: string }) =>
    textEnvelope(target.ref, `preview of ${target.ref}`),
  );
  // Each test owns a clean envelope cache (the store is a global singleton).
  useAppStore.getState().clearPreviewEnvelopeCache();
  // #1713 — the plot Run result is shared via the store; reset between tests.
  useAppStore.getState().setPlotPreviewTarget(null);
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

  // #1713 — the plot list, Run, and Relink moved to the dedicated Plots tab
  // (see PlotsTab.test.tsx). DataPreview renders the Run result the Plots tab
  // publishes into the store, but ONLY when the plot's linked block is selected
  // (the result belongs to that block; it must not appear in the empty state).
  it("shows the plot result only when its linked block is selected (#1713)", async () => {
    const plotTarget = {
      kind: "plot_artifact" as const,
      ref: "data-plot-1",
      recorded_type: "PlotArtifact",
      type_chain: ["DataObject", "PlotArtifact"],
      source: { workflow_id: "main", node_id: "node-1", output_port: "output" },
    };

    const { rerender } = render(
      <DataPreview blockOutputs={{}} selectedNodeId={null} selectedNodeLabel="" />,
    );

    // The Plots tab publishes a Run result, but no block is selected → the plot
    // is NOT shown; the empty state stays and no plot_artifact session is made.
    act(() => useAppStore.getState().setPlotPreviewTarget(plotTarget));
    expect(screen.getByText(/Pick a block/i)).toBeInTheDocument();
    expect(createPreviewSession).not.toHaveBeenCalledWith(
      expect.objectContaining({ kind: "plot_artifact" }),
      expect.anything(),
    );

    // Selecting the plot's linked block surfaces the result via PreviewHost.
    rerender(
      <DataPreview
        blockOutputs={{ "node-1": {} }}
        selectedNodeId="node-1"
        selectedNodeLabel="Block"
      />,
    );
    await waitFor(() => {
      expect(createPreviewSession).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "plot_artifact", ref: "data-plot-1" }),
        expect.anything(),
      );
    });
    await waitFor(() => expect(screen.getByTestId("preview-host")).toBeInTheDocument());
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

  // #1795 — the maximize control pops the active preview into a floating window
  // so a cramped right-sidebar preview can be inspected at a larger size.
  it("offers no maximize control without previewable output (#1795)", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": {} }}
        selectedNodeId="node-1"
        selectedNodeLabel="Empty Block"
      />,
    );
    expect(screen.queryByRole("button", { name: "Maximize preview" })).not.toBeInTheDocument();
  });

  it("maximizes the active preview into an overlay window and closes on Escape (#1795)", async () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "data-123" } } }}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    const maximize = await screen.findByRole("button", { name: "Maximize preview" });
    expect(screen.queryByTestId("preview-maximized-overlay")).not.toBeInTheDocument();

    fireEvent.click(maximize);
    expect(screen.getByTestId("preview-maximized-overlay")).toBeInTheDocument();
    // The same host stays mounted inside the maximized window.
    await waitFor(() => expect(screen.getByTestId("preview-host")).toBeInTheDocument());

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("preview-maximized-overlay")).not.toBeInTheDocument(),
    );
  });

  // #1795 audit P2 — maximizing must NOT remount PreviewHost. PreviewHost owns
  // the query/drill-down state and creates the preview session on mount, so a
  // remount would reset the active preview (paging, slice, drill-down) and open
  // a fresh session. The single host is reconciled in place, so its DOM node is
  // reused and no extra session is created when popping out and back.
  it("preserves the same PreviewHost instance across maximize/restore (#1795)", async () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "data-123" } } }}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    const hostBefore = await screen.findByTestId("preview-host");
    const sessionsAfterMount = createPreviewSession.mock.calls.length;

    // Maximize: the host DOM node is reused (in-place reconcile, not remount)
    // and no new preview session is opened.
    fireEvent.click(screen.getByRole("button", { name: "Maximize preview" }));
    const hostMaximized = screen.getByTestId("preview-host");
    expect(hostMaximized).toBe(hostBefore);

    // Restore (Esc): still the same node, still no extra session.
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("preview-maximized-overlay")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("preview-host")).toBe(hostBefore);
    expect(createPreviewSession.mock.calls.length).toBe(sessionsAfterMount);
  });

  it("closes the maximized window via the close control and backdrop (#1795)", async () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "data-123" } } }}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    // Close control dismisses it.
    fireEvent.click(await screen.findByRole("button", { name: "Maximize preview" }));
    fireEvent.click(screen.getByRole("button", { name: "Close preview window" }));
    expect(screen.queryByTestId("preview-maximized-overlay")).not.toBeInTheDocument();

    // Re-open, then a backdrop click dismisses it.
    fireEvent.click(screen.getByRole("button", { name: "Maximize preview" }));
    fireEvent.click(screen.getByTestId("preview-maximized-overlay"));
    expect(screen.queryByTestId("preview-maximized-overlay")).not.toBeInTheDocument();
  });
});
