/**
 * ADR-054 Phase D (#2354) — the MiniApp target picker (FR-034).
 *
 * US6 acceptance 1: opening a MiniApp from its card lists the outputs of the
 * project's latest successful runs that its declared type can read, and the
 * MiniApp opens on the chosen one.
 *
 * THE FILTER BEING PINNED HERE IS "ASKS THE ROUTE", not "reimplements the
 * subtype rule". `GET /api/panels/miniapps/{id}/sources` returns only the
 * matching outputs, because the type hierarchy is runtime truth and lives on
 * the backend; the thing this component could get wrong is listing something
 * the route did not return, or quietly dropping something it did. Both are
 * asserted.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MiniAppTargetPicker } from "./MiniAppTargetPicker";
import type { MiniAppSource, MiniAppSummary } from "./types";

const THRESHOLD: MiniAppSummary = {
  panel_id: "threshold",
  name: "Threshold explorer",
  description: "",
  type: "Image",
  tier: "project",
  directory: "/p/panels/threshold",
  has_python: true,
};

function source(overrides: Partial<MiniAppSource> & { block_id: string }): MiniAppSource {
  return {
    workflow_id: "main",
    workflow_name: "Main",
    block_name: overrides.block_id,
    port: "out",
    type: "Image",
    ...overrides,
  };
}

/** What the route returns: two workflows, three Image outputs. */
const SOURCES: MiniAppSource[] = [
  source({ block_id: "segment1", block_name: "Segment", port: "mask", type: "Mask" }),
  source({ block_id: "pair1", block_name: "Pair", port: "left" }),
  source({
    block_id: "denoise1",
    block_name: "Denoise",
    workflow_id: "other",
    workflow_name: "Other",
  }),
];

function renderPicker(
  options: {
    sources?: MiniAppSource[] | (() => Promise<MiniAppSource[]>);
    restrictTo?: { workflow_id: string; block_id: string } | null;
  } = {},
) {
  const onPick = vi.fn();
  const onOpenChange = vi.fn();
  const rows = options.sources ?? SOURCES;
  const fetchSources = vi.fn(async () => (typeof rows === "function" ? rows() : rows));
  render(
    <MiniAppTargetPicker
      onOpenChange={onOpenChange}
      onPick={onPick}
      open
      restrictTo={options.restrictTo ?? null}
      sources={fetchSources as never}
      summary={THRESHOLD}
    />,
  );
  return { onPick, onOpenChange, fetchSources };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MiniAppTargetPicker (ADR-054 FR-034)", () => {
  it("closes from the icon-only header button without submitting", async () => {
    const harness = renderPicker();
    await screen.findByTestId("miniapp-target-row-main-segment1-mask");

    const close = screen.getByRole("button", { name: "Close" });
    expect(close.textContent).toBe("");
    fireEvent.click(close);

    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
    expect(harness.onPick).not.toHaveBeenCalled();
  });

  it("lists the outputs the route returned, by workflow, block and port", async () => {
    const harness = renderPicker();

    await waitFor(() =>
      expect(screen.getByTestId("miniapp-target-row-main-segment1-mask")).toBeInTheDocument(),
    );
    expect(harness.fetchSources).toHaveBeenCalledWith("threshold");
    expect(screen.getByTestId("miniapp-target-row-main-pair1-left")).toBeInTheDocument();
    expect(screen.getByTestId("miniapp-target-row-other-denoise1-out")).toBeInTheDocument();
    // Grouped by workflow, so a project with several is readable.
    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.getByText("Other")).toBeInTheDocument();
  });

  it("distinguishes same-name nodes and opens the selected instance", async () => {
    const harness = renderPicker({
      sources: [
        source({ block_id: "load_one", block_name: "load_data", port: "data", type: "Array" }),
        source({ block_id: "load_two", block_name: "load_data", port: "data", type: "Array" }),
        source({ block_id: "load_three", port: "data", type: "Array" }),
      ],
    });

    expect(
      await screen.findByRole("button", { name: "load_data [load_one] - data (Array)" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "load_three - data (Array)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "load_data [load_two] - data (Array)" }));

    expect(harness.onPick).toHaveBeenCalledWith({
      workflow_id: "main",
      block_id: "load_two",
      port: "data",
    });
    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("opens the MiniApp on the chosen output", async () => {
    const harness = renderPicker();
    await waitFor(() =>
      expect(screen.getByTestId("miniapp-target-row-main-segment1-mask")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("miniapp-target-row-main-segment1-mask"));

    expect(harness.onPick).toHaveBeenCalledWith({
      workflow_id: "main",
      block_id: "segment1",
      port: "mask",
    });
    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("narrows to one block when the canvas asked about a block", async () => {
    // FR-034's context-menu half: opening from a block uses THAT block's
    // output, and only asks because several of its ports matched.
    renderPicker({ restrictTo: { workflow_id: "main", block_id: "pair1" } });

    await waitFor(() =>
      expect(screen.getByTestId("miniapp-target-row-main-pair1-left")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("miniapp-target-row-main-segment1-mask")).toBeNull();
    expect(screen.queryByTestId("miniapp-target-row-other-denoise1-out")).toBeNull();
  });

  it("says so when nothing in the project is of the declared type", async () => {
    renderPicker({ sources: [] });

    await waitFor(() => expect(screen.getByTestId("miniapp-target-empty")).toBeInTheDocument());
    expect(screen.getByTestId("miniapp-target-empty")).toHaveTextContent("Image");
  });

  it("renders nothing when it is closed or has no MiniApp", () => {
    const sources = vi.fn(async () => SOURCES);
    render(
      <MiniAppTargetPicker
        onOpenChange={vi.fn()}
        onPick={vi.fn()}
        open={false}
        sources={sources as never}
        summary={THRESHOLD}
      />,
    );
    expect(screen.queryByTestId("miniapp-target-picker")).toBeNull();
    expect(sources).not.toHaveBeenCalled();
  });
});
