import { render, waitFor, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope } from "../types/api";

// Mock only PreviewHost's session methods; keep every other lib/api export
// intact (the Zustand store imports named helpers from this module at init).
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
    expect(screen.getByText(/no previewable outputs/i)).toBeInTheDocument();
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
            images: {
              kind: "collection",
              items: [{ data_ref: "data-a" }, { data_ref: "data-b" }],
            },
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

  // #898 — pill labels show source filename (independent of the renderer).
  it("pill label shows source filename when framework.source is set (#898)", () => {
    render(
      <DataPreview
        blockOutputs={{
          "load-1": {
            images: {
              kind: "collection",
              items: [
                {
                  data_ref: "data-abcdef",
                  metadata: { framework: { source: "C:/data/beads.tif" } },
                },
                {
                  data_ref: "data-123456",
                  metadata: { meta: { source_file: "/home/u/sample_002.tif" } },
                },
                { data_ref: "data-xyz789", metadata: { framework: { source: "" } } },
              ],
            },
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
