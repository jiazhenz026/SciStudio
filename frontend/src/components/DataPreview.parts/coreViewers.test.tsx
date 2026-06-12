/**
 * ADR-048 SPEC 1 — ArrayViewer numeric heatmap tests (FR-013 / FR-014, #1603).
 *
 * Pins the PyCharm-style numeric array viewer behavior:
 *   - the displayed 2-D plane renders the ACTUAL numeric values in a table;
 *   - each cell is heatmap-colored, and signed data is NOT all-black (a real
 *     diverging colormap — negatives map to a distinct color, not 0/black);
 *   - a value-scale legend shows min..max;
 *   - one slice selector is rendered per non-displayed axis, and changing it
 *     patches the session query with a per-axis ``axis_indices`` map.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope } from "../../types/api";

import {
  ArrayHeatmapTable,
  ArrayLegend,
  ArrayViewer,
  formatCell,
  heatmapColor,
} from "./coreViewers";

afterEach(cleanup);

function arrayEnvelope(payload: Record<string, unknown>): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "core.array.basic",
    target: { kind: "data_ref", ref: "data-1" },
    kind: "array",
    payload,
    resources: [],
    metadata: { sampled: false, truncated: false, cached: false, derived: false, complete: true },
    diagnostics: [],
    error: null,
  } as unknown as PreviewEnvelope;
}

describe("heatmapColor (pure)", () => {
  it("maps signed data to a diverging scale — negatives are NOT black", () => {
    const neg = heatmapColor(-5, -5, 5);
    const pos = heatmapColor(5, -5, 5);
    const zero = heatmapColor(0, -5, 5);
    // None of the diverging endpoints collapse to black (the old PNG bug).
    expect(neg).not.toBe("rgb(0, 0, 0)");
    expect(pos).not.toBe("rgb(0, 0, 0)");
    // Negative and positive extremes are visibly distinct colors.
    expect(neg).not.toBe(pos);
    // Center is near-white.
    expect(zero).toBe("rgb(247, 247, 247)");
  });

  it("renders non-finite values transparent", () => {
    expect(heatmapColor(Number.NaN, 0, 1)).toBe("transparent");
    expect(heatmapColor(Number.POSITIVE_INFINITY, 0, 1)).toBe("transparent");
  });

  it("uses a sequential scale for all-nonnegative data", () => {
    const lo = heatmapColor(0, 0, 10);
    const hi = heatmapColor(10, 0, 10);
    expect(lo).not.toBe(hi);
  });
});

describe("formatCell (pure)", () => {
  it("keeps small integers exact and uses exponent for extreme magnitudes", () => {
    expect(formatCell(0)).toBe("0");
    expect(formatCell(42)).toBe("42");
    expect(formatCell(-7)).toBe("-7");
    expect(formatCell(123456789)).toBe("1.23e+8");
    expect(formatCell(0.0001)).toBe("1.00e-4");
    expect(formatCell(Number.NaN)).toBe("NaN");
  });
});

describe("ArrayHeatmapTable", () => {
  it("renders the actual numeric values as table cells with heatmap backgrounds", () => {
    render(
      <ArrayHeatmapTable
        matrix={[
          [-2, 0, 2],
          [4, -4, 1],
        ]}
        vmin={-4}
        vmax={4}
        shape={[2, 3]}
      />,
    );
    // Real numbers are visible (not a gray blob).
    expect(screen.getByTestId("array-cell-0-0")).toHaveTextContent("-2");
    expect(screen.getByTestId("array-cell-1-0")).toHaveTextContent("4");
    // The negative cell has a colored (non-transparent, non-black) background.
    const negCell = screen.getByTestId("array-cell-1-1");
    const bg = negCell.style.backgroundColor;
    expect(bg).not.toBe("");
    expect(bg).not.toBe("transparent");
    expect(bg).not.toBe("rgb(0, 0, 0)");
  });
});

describe("ArrayLegend", () => {
  it("shows the min and max value labels", () => {
    render(<ArrayLegend vmin={-4} vmax={5} />);
    expect(screen.getByTestId("array-legend-min")).toHaveTextContent("-4");
    expect(screen.getByTestId("array-legend-max")).toHaveTextContent("5");
  });
});

describe("ArrayViewer — numeric heatmap + per-axis slice selectors", () => {
  const ndPayload = {
    shape: [4, 6, 2, 3],
    dtype: "float64",
    axes: ["t", "z", "y", "x"],
    ndim: 4,
    matrix: [
      [-1, 0, 2],
      [3, -4, 5],
    ],
    vmin: -4,
    vmax: 5,
    slice_axes: [
      { axis: 0, name: "t", size: 4, index: 1 },
      { axis: 1, name: "z", size: 6, index: 2 },
    ],
    src: "data:image/png;base64,IGNORED",
  };

  it("renders the numeric table + legend and one selector per non-displayed axis", () => {
    render(<ArrayViewer envelope={arrayEnvelope(ndPayload)} />);
    expect(screen.getByTestId("array-2d-heatmap")).toBeInTheDocument();
    expect(screen.getByTestId("array-legend")).toBeInTheDocument();
    // Two extra axes → two slice rows (fully navigable, not just one face).
    expect(screen.getByTestId("array-slice-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("array-slice-row-1")).toBeInTheDocument();
    // The echoed per-axis indices drive the controls.
    expect(screen.getByTestId("array-slice-slider-1")).toHaveValue("2");
    // Real values, not an <img> raster.
    expect(screen.queryByAltText("Array preview")).toBeNull();
    expect(screen.getByTestId("array-cell-1-1")).toHaveTextContent("-4");
  });

  it("patches the session query with a per-axis axis_indices map on change", () => {
    const onPatchQuery = vi.fn();
    render(<ArrayViewer envelope={arrayEnvelope(ndPayload)} onPatchQuery={onPatchQuery} />);

    fireEvent.change(screen.getByTestId("array-slice-slider-1"), { target: { value: "4" } });

    expect(onPatchQuery).toHaveBeenCalledTimes(1);
    const patch = onPatchQuery.mock.calls[0][0] as Record<string, unknown>;
    // Carries the full per-axis selection (axis 0 stays at its echoed index).
    expect(patch.axis_indices).toEqual({ "0": 1, "1": 4 });
    // Changing a non-first axis must NOT move the legacy slice_index control.
    expect(patch.slice_index).toBeUndefined();
  });

  it("keeps slice_index in sync when the first extra axis changes", () => {
    const onPatchQuery = vi.fn();
    render(<ArrayViewer envelope={arrayEnvelope(ndPayload)} onPatchQuery={onPatchQuery} />);

    fireEvent.change(screen.getByTestId("array-slice-slider-0"), { target: { value: "3" } });

    const patch = onPatchQuery.mock.calls[0][0] as Record<string, unknown>;
    expect(patch.axis_indices).toEqual({ "0": 3, "1": 2 });
    expect(patch.slice_index).toBe(3);
  });

  it("renders a scalar value for a 0-D array", () => {
    render(
      <ArrayViewer
        envelope={arrayEnvelope({ shape: [], dtype: "float64", ndim: 0, matrix: [[42]] })}
      />,
    );
    expect(screen.getByTestId("array-scalar")).toHaveTextContent("42");
  });
});
