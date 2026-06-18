import { describe, expect, it } from "vitest";

import { isPlotRenderFilePath, suggestPlotContextCompletions } from "./plotCompletions";

describe("plotCompletions", () => {
  it("detects plot render files only", () => {
    expect(isPlotRenderFilePath("plots/qc/render.py")).toBe(true);
    expect(isPlotRenderFilePath("plots/qc/render.R")).toBe(true);
    expect(isPlotRenderFilePath("blocks/render.py")).toBe(false);
    expect(isPlotRenderFilePath("plots/qc/helper.py")).toBe(false);
  });

  it("suggests Python context helpers for plot render scripts", () => {
    const suggestions = suggestPlotContextCompletions({
      language: "python",
      filePath: "plots/qc/render.py",
      linePrefix: "    context.",
    }).map((item) => item.label);
    expect(suggestions).toEqual(
      expect.arrayContaining(["to_dataframe", "items", "plt", "save_figure", "save_plot"]),
    );
  });

  it("suggests R context helpers for plot render scripts", () => {
    const suggestions = suggestPlotContextCompletions({
      language: "r",
      filePath: "plots/qc/render.R",
      linePrefix: "  context$",
    }).map((item) => item.label);
    expect(suggestions).toEqual(
      expect.arrayContaining(["to_dataframe", "save_plot", "save_figure"]),
    );
  });

  it("does not leak plot-only helpers into ordinary scripts", () => {
    expect(
      suggestPlotContextCompletions({
        language: "python",
        filePath: "blocks/sample.py",
        linePrefix: "context.",
      }),
    ).toEqual([]);
  });
});
