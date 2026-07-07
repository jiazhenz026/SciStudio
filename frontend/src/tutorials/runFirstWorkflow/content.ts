import type {
  BlockSummary,
  PlotListItem,
  RunFirstWorkflowBootstrapResponse,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import type {
  RunFirstWorkflowTutorialInstance,
  RunFirstWorkflowTutorialStep,
} from "../../store/types";

export const RUN_FIRST_WORKFLOW_TUTORIAL_ID = "run-first-scistudio-workflow" as const;

export function instanceFromBootstrap(
  response: RunFirstWorkflowBootstrapResponse,
): RunFirstWorkflowTutorialInstance {
  return {
    tutorialId: response.tutorial_id,
    projectId: response.project.id,
    datasetPath: response.dataset_path,
    workflowId: response.workflow_id,
    customBlockPath: response.custom_block_path,
    customBlockType: response.custom_block_type,
    customBlockName: response.custom_block_name,
    plotId: response.plot_id,
    plotTitle: response.plot_title,
    negativeControl: response.negative_control,
    positiveControl: response.positive_control,
  };
}

export const NORMALIZE_FLUORESCENCE_BLOCK_SOURCE = `from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class NormalizeFluorescenceBlock(ProcessBlock):
    """Normalize fluorescence using negative and positive control means."""

    name: ClassVar[str] = "Normalize Fluorescence"
    type_name: ClassVar[str] = "normalize_fluorescence"
    description: ClassVar[str] = "Normalize fluorescence with negative and positive controls."
    algorithm: ClassVar[str] = "fluorescence_control_normalization"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Raw fluorescence table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[DataFrame], description="Normalized activity table"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "negative_control": {
                "type": "string",
                "default": "neg_control",
                "description": "Condition label used as the zero-activity control.",
            },
            "positive_control": {
                "type": "string",
                "default": "pos_control",
                "description": "Condition label used as the full-activity control.",
            },
        },
        "required": ["negative_control", "positive_control"],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        df = item.to_pandas().copy()
        negative_control = str(config.get("negative_control", "neg_control"))
        positive_control = str(config.get("positive_control", "pos_control"))

        required = {"condition", "replicate", "fluorescence"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Input table is missing columns: {sorted(missing)}")

        neg = df.loc[df["condition"] == negative_control, "fluorescence"]
        pos = df.loc[df["condition"] == positive_control, "fluorescence"]
        if neg.empty or pos.empty:
            raise ValueError("Both negative_control and positive_control labels must exist in condition.")

        neg_mean = float(neg.mean())
        pos_mean = float(pos.mean())
        denominator = pos_mean - neg_mean
        if denominator == 0:
            raise ValueError("Positive and negative control means must be different.")

        df["normalized_activity"] = (df["fluorescence"] - neg_mean) / denominator
        out = pa.Table.from_pandas(df, preserve_index=False)
        return DataFrame(data=out)
`;

export const NORMALIZED_ACTIVITY_PLOT_SOURCE = `from __future__ import annotations


def render(collection):
    """Plot normalized activity by condition."""
    import matplotlib.pyplot as plt
    import numpy as np

    df = collection.items.open_one()
    order = ["neg_control", "treated_1uM", "treated_5uM", "pos_control"]
    present = [condition for condition in order if condition in set(df["condition"])]
    grouped = df.groupby("condition")["normalized_activity"]
    means = grouped.mean().reindex(present)
    std = grouped.std().reindex(present).fillna(0)

    x = np.arange(len(present))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(x, means.to_numpy(), yerr=std.to_numpy(), capsize=4, color="#2d7891", alpha=0.82)

    for idx, condition in enumerate(present):
        values = df.loc[df["condition"] == condition, "normalized_activity"].to_numpy()
        jitter = np.linspace(-0.09, 0.09, len(values)) if len(values) > 1 else np.array([0.0])
        ax.scatter(idx + jitter, values, color="#1c211b", s=24, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(["Neg control", "1 uM treated", "5 uM treated", "Pos control"], rotation=15, ha="right")
    ax.set_ylabel("Normalized activity")
    ax.set_title("Normalized cell activity")
    ax.axhline(0, color="#78716c", linewidth=0.8)
    ax.axhline(1, color="#78716c", linewidth=0.8, linestyle="--")
    fig.tight_layout()
    return fig
`;

export interface TutorialStepCopy {
  id: RunFirstWorkflowTutorialStep;
  title: string;
  body: string;
  actionLabel?: string;
}

export const RUN_FIRST_WORKFLOW_INITIAL_STEP: TutorialStepCopy = {
  id: "inspect-data",
  title: "Inspect sample data",
  body: "Open the fluorescence table and look at the negative control, treated, and positive control rows.",
  actionLabel: "Open data",
};

export const RUN_FIRST_WORKFLOW_STEPS: TutorialStepCopy[] = [
  RUN_FIRST_WORKFLOW_INITIAL_STEP,
  {
    id: "create-custom-block",
    title: "Create your normalization block",
    body: "Create a project-local custom block. SciStudio will fill in the normalization code for this tutorial.",
    actionLabel: "Create block",
  },
  {
    id: "build-workflow",
    title: "Build the workflow",
    body: "Drag Load into the canvas, drag Normalize Fluorescence into the canvas, then connect Load data to Normalize table.",
  },
  {
    id: "configure-controls",
    title: "Configure data path",
    body: "Select the Load block and set path to data/raw/cell_viability_fluorescence.csv. Keep core_type as DataFrame.",
  },
  {
    id: "run-workflow",
    title: "Run the workflow",
    body: "Run the workflow and wait for Normalize Fluorescence to produce its normalized output.",
  },
  {
    id: "create-plot-card",
    title: "Create a plot card",
    body: "Create a plot card from the normalized output. SciStudio will fill in the plot code for this tutorial.",
    actionLabel: "Create plot card",
  },
  {
    id: "view-history",
    title: "View history",
    body: "Open History and review the workflow run that produced your normalized table.",
    actionLabel: "Open history",
  },
  {
    id: "finish",
    title: "Finish",
    body: "You have completed your first SciStudio workflow.",
    actionLabel: "Finish tutorial",
  },
];

export function findStep(id: RunFirstWorkflowTutorialStep): TutorialStepCopy {
  return RUN_FIRST_WORKFLOW_STEPS.find((step) => step.id === id) ?? RUN_FIRST_WORKFLOW_INITIAL_STEP;
}

export function hasTutorialBlock(
  blocks: BlockSummary[],
  instance: RunFirstWorkflowTutorialInstance,
): boolean {
  return blocks.some(
    (block) =>
      block.type_name === instance.customBlockType || block.name === instance.customBlockName,
  );
}

export function workflowHasTutorialGraph(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
  instance: RunFirstWorkflowTutorialInstance,
): boolean {
  const loadNode = nodes.find((node) => node.block_type === "load_data");
  const normalizeNode = nodes.find((node) => node.block_type === instance.customBlockType);
  if (!loadNode || !normalizeNode) return false;
  return edges.some(
    (edge) => edge.source === `${loadNode.id}:data` && edge.target === `${normalizeNode.id}:table`,
  );
}

function pathMatchesTutorialDataset(value: unknown, datasetPath: string): boolean {
  const expected = datasetPath.replace(/\\/g, "/");
  const candidates = Array.isArray(value) ? value : [value];
  return candidates.some((candidate) => {
    if (typeof candidate !== "string") return false;
    const normalized = candidate.trim().replace(/\\/g, "/");
    return normalized === expected || normalized.endsWith(`/${expected}`);
  });
}

export function workflowHasTutorialDatasetPath(
  nodes: WorkflowNode[],
  instance: RunFirstWorkflowTutorialInstance,
): boolean {
  const loadNode = nodes.find((node) => node.block_type === "load_data");
  const params = loadNode?.config?.params as Record<string, unknown> | undefined;
  return pathMatchesTutorialDataset(params?.path, instance.datasetPath);
}

export function normalizeOutputAvailable(
  blockOutputs: Record<string, Record<string, unknown>>,
  nodes: WorkflowNode[],
  instance: RunFirstWorkflowTutorialInstance,
): boolean {
  const normalizeNode = nodes.find((node) => node.block_type === instance.customBlockType);
  if (!normalizeNode) return false;
  return blockOutputs[normalizeNode.id]?.normalized !== undefined;
}

export function hasTutorialPlot(
  plots: PlotListItem[],
  instance: RunFirstWorkflowTutorialInstance,
): boolean {
  return plots.some((plot) => plot.plot_id === instance.plotId);
}
