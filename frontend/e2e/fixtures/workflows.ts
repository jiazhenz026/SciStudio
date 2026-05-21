import fs from "node:fs/promises";
import path from "node:path";

export type E2EWorkflow = {
  workflowId: string;
  workflowPath: string;
  expectedOutputPath: string;
  workflow: {
    id: string;
    version: string;
    description: string;
    nodes: Array<{
      id: string;
      block_type: string;
      config: Record<string, unknown>;
      layout?: { x: number; y: number };
    }>;
    edges: Array<{ source: string; target: string }>;
    metadata?: Record<string, unknown>;
  };
};

function yamlString(value: unknown): string {
  return JSON.stringify(value);
}

export function workflowYaml(fixture: E2EWorkflow): string {
  const lines: string[] = [
    `id: ${fixture.workflow.id}`,
    `version: ${yamlString(fixture.workflow.version)}`,
    `description: ${yamlString(fixture.workflow.description)}`,
    "nodes:",
  ];
  for (const node of fixture.workflow.nodes) {
    lines.push(`  - id: ${node.id}`);
    lines.push(`    block_type: ${node.block_type}`);
    if (node.layout) {
      lines.push("    layout:");
      lines.push(`      x: ${node.layout.x}`);
      lines.push(`      y: ${node.layout.y}`);
    }
    lines.push("    config:");
    for (const [key, value] of Object.entries(node.config)) {
      lines.push(`      ${key}: ${yamlString(value)}`);
    }
  }
  lines.push("edges:");
  for (const edge of fixture.workflow.edges) {
    lines.push(`  - source: ${edge.source}`);
    lines.push(`    target: ${edge.target}`);
  }
  lines.push("metadata:");
  lines.push("  fixture: issue-1384-e2e-discovery");
  return `${lines.join("\n")}\n`;
}

export async function writeWorkflowFixture(projectRoot: string, fixture: E2EWorkflow): Promise<string> {
  const workflowPath = path.join(projectRoot, fixture.workflowPath);
  await fs.mkdir(path.dirname(workflowPath), { recursive: true });
  await fs.writeFile(workflowPath, workflowYaml(fixture), "utf-8");
  return workflowPath;
}

const baseNodes = [
  {
    id: "load_image",
    block_type: "imaging.load_image",
    layout: { x: 80, y: 120 },
    config: { params: { path: "data/raw/synthetic-fluorescence.tif" } },
  },
  {
    id: "threshold",
    block_type: "imaging.threshold",
    layout: { x: 360, y: 120 },
    config: { params: { method: "otsu" } },
  },
  {
    id: "save_threshold",
    block_type: "imaging.save_image",
    layout: { x: 640, y: 120 },
    config: {
      params: {
        path: "data/artifacts/threshold-mask.tif",
        capability_id: "scistudio-blocks-imaging.image.tiff.save",
      },
    },
  },
];

const baseEdges = [
  { source: "load_image:images", target: "threshold:image" },
  { source: "threshold:mask", target: "save_threshold:images" },
];

export const minimalLoadThresholdSaveWorkflow: E2EWorkflow = {
  workflowId: "minimal-image-threshold-save",
  workflowPath: "workflows/minimal-image-threshold-save.yaml",
  expectedOutputPath: "data/artifacts/threshold-mask.tif",
  workflow: {
    id: "minimal-image-threshold-save",
    version: "1.0.0",
    description: "E2E minimal load image, threshold, save workflow.",
    nodes: baseNodes,
    edges: baseEdges,
    metadata: { fixture: "minimal" },
  },
};

export const invalidThresholdWorkflow: E2EWorkflow = {
  ...minimalLoadThresholdSaveWorkflow,
  workflowId: "invalid-threshold",
  workflowPath: "workflows/invalid-threshold.yaml",
  workflow: {
    ...minimalLoadThresholdSaveWorkflow.workflow,
    id: "invalid-threshold",
    nodes: baseNodes.map((node) =>
      node.id === "threshold"
        ? { ...node, config: { params: { method: "not-a-real-threshold-method" } } }
        : node,
    ),
  },
};

export const failingLoadImageWorkflow: E2EWorkflow = {
  ...minimalLoadThresholdSaveWorkflow,
  workflowId: "failing-load-image",
  workflowPath: "workflows/failing-load-image.yaml",
  workflow: {
    ...minimalLoadThresholdSaveWorkflow.workflow,
    id: "failing-load-image",
    nodes: baseNodes.map((node) =>
      node.id === "load_image"
        ? { ...node, config: { params: { path: "data/raw/missing-image.tif" } } }
        : node,
    ),
  },
};

export const slowCancellableWorkflow: E2EWorkflow = {
  ...minimalLoadThresholdSaveWorkflow,
  workflowId: "slow-cancellable",
  workflowPath: "workflows/slow-cancellable.yaml",
  workflow: {
    ...minimalLoadThresholdSaveWorkflow.workflow,
    id: "slow-cancellable",
    description: "E2E cancellable workflow fixture.",
  },
};
