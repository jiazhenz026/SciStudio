import { describe, expect, it } from "vitest";

import type { RunFirstWorkflowTutorialInstance } from "../../store/types";
import type { BlockSummary, PlotListItem, WorkflowEdge, WorkflowNode } from "../../types/api";
import {
  hasTutorialBlock,
  hasTutorialPlot,
  NORMALIZE_FLUORESCENCE_BLOCK_SOURCE,
  NORMALIZED_ACTIVITY_PLOT_SOURCE,
  normalizeOutputAvailable,
  workflowHasTutorialDatasetPath,
  workflowHasTutorialGraph,
} from "./content";

const instance: RunFirstWorkflowTutorialInstance = {
  tutorialId: "run-first-scistudio-workflow",
  projectId: "p1",
  datasetPath: "data/raw/cell_viability_fluorescence.csv",
  workflowId: "main",
  customBlockPath: "blocks/normalize_fluorescence.py",
  customBlockType: "normalize_fluorescence",
  customBlockName: "Normalize Fluorescence",
  plotId: "normalized_activity_plot",
  plotTitle: "Normalized activity by condition",
  negativeControl: "neg_control",
  positiveControl: "pos_control",
};

describe("Run First Workflow tutorial content", () => {
  it("ships concrete normalization and plot code, not generic templates", () => {
    expect(NORMALIZE_FLUORESCENCE_BLOCK_SOURCE).toContain("class NormalizeFluorescenceBlock");
    expect(NORMALIZE_FLUORESCENCE_BLOCK_SOURCE).toContain("ProcessBlock");
    expect(NORMALIZE_FLUORESCENCE_BLOCK_SOURCE).toContain("def process_item");
    expect(NORMALIZE_FLUORESCENCE_BLOCK_SOURCE).toContain("normalized_activity");
    expect(NORMALIZE_FLUORESCENCE_BLOCK_SOURCE).toContain("neg_control");
    expect(NORMALIZED_ACTIVITY_PLOT_SOURCE).toContain("Normalized cell activity");
    expect(NORMALIZED_ACTIVITY_PLOT_SOURCE).toContain("treated_5uM");
  });

  it("detects the tutorial custom block in the palette", () => {
    const blocks = [
      {
        name: "Normalize Fluorescence",
        type_name: "normalize_fluorescence",
      } as BlockSummary,
    ];
    expect(hasTutorialBlock(blocks, instance)).toBe(true);
  });

  it("detects the required load-to-normalize workflow graph", () => {
    const nodes: WorkflowNode[] = [
      { id: "load-1", block_type: "load_data", config: { params: {} } },
      { id: "norm-1", block_type: "normalize_fluorescence", config: { params: {} } },
    ];
    const edges: WorkflowEdge[] = [{ source: "load-1:data", target: "norm-1:table" }];

    expect(workflowHasTutorialGraph(nodes, edges, instance)).toBe(true);
  });

  it("detects the configured Load dataset path and normalized output", () => {
    const nodes: WorkflowNode[] = [
      {
        id: "load-1",
        block_type: "load_data",
        config: { params: { path: "/tmp/project/data/raw/cell_viability_fluorescence.csv" } },
      },
      {
        id: "norm-1",
        block_type: "normalize_fluorescence",
        config: { params: {} },
      },
    ];

    expect(workflowHasTutorialDatasetPath(nodes, instance)).toBe(true);
    expect(
      normalizeOutputAvailable(
        { "norm-1": { normalized: { path: "out.parquet" } } },
        nodes,
        instance,
      ),
    ).toBe(true);
  });

  it("detects the tutorial plot card", () => {
    const plot = {
      plot_id: "normalized_activity_plot",
      title: "Normalized activity by condition",
    } as PlotListItem;

    expect(hasTutorialPlot([plot], instance)).toBe(true);
  });
});
