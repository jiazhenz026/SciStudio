import { describe, expect, it } from "vitest";

import type { BlockSchemaResponse, BlockSummary, PlotTargetItem } from "../types/api";
import { describeReadableTargets, targetBlockLabel } from "./plotTargetLabel";

function target(overrides: Partial<PlotTargetItem>): PlotTargetItem {
  return {
    target_id: "t-a",
    workflow_path: "workflows/main.yaml",
    workflow_id: "main",
    node_id: "demo_block-1",
    node_label: "",
    block_type: "demo_block",
    output_port: "out",
    output_type: "Spectrum",
    is_collection: false,
    latest_run_id: "run-1",
    latest_output_available: true,
    diagnostics: [],
    ...overrides,
  };
}

function summary(typeName: string, name: string): BlockSummary {
  return { name, type_name: typeName } as BlockSummary;
}

const schemas: Record<string, BlockSchemaResponse> = {};

describe("targetBlockLabel", () => {
  it("uses the registry display name, never the opaque node_id", () => {
    const blocks = [summary("demo_block", "Demo Block")];
    expect(targetBlockLabel(target({ node_id: "demo_block-123" }), blocks, schemas)).toBe(
      "Demo Block",
    );
  });

  it("prefers an explicit user label over the registry name", () => {
    const blocks = [summary("demo_block", "Demo Block")];
    expect(targetBlockLabel(target({ node_label: "My QC step" }), blocks, schemas)).toBe(
      "My QC step",
    );
  });

  it("falls back to the block_type when the block is not in the registry", () => {
    expect(targetBlockLabel(target({ block_type: "unknown_block" }), [], schemas)).toBe(
      "unknown_block",
    );
  });
});

describe("describeReadableTargets", () => {
  it("renders '<block> · <port>' without the node_id", () => {
    const blocks = [summary("demo_block", "Demo Block")];
    const map = describeReadableTargets([target({ target_id: "t1" })], blocks, schemas);
    const row = map.get("t1");
    expect(row?.primary).toBe("Demo Block · out");
    expect(row?.primary).not.toContain("demo_block-1");
    expect(row?.outputType).toBe("Spectrum");
    expect(row?.pending).toBe(false);
  });

  it("appends a stable #index only when two blocks share a display name", () => {
    const blocks = [summary("demo_block", "Demo Block")];
    const map = describeReadableTargets(
      [
        target({ target_id: "t1", node_id: "demo_block-200" }),
        target({ target_id: "t2", node_id: "demo_block-100" }),
      ],
      blocks,
      schemas,
    );
    // Index follows sorted node_id, independent of input order: -100 → #1, -200 → #2.
    expect(map.get("t2")?.blockLabel).toBe("Demo Block #1");
    expect(map.get("t1")?.blockLabel).toBe("Demo Block #2");
  });

  it("does not index a unique block name and shares one index across that node's ports", () => {
    const blocks = [summary("demo_block", "Demo Block"), summary("other_block", "Other Block")];
    const map = describeReadableTargets(
      [
        target({ target_id: "t1", node_id: "demo_block-1", output_port: "a" }),
        target({ target_id: "t2", node_id: "demo_block-1", output_port: "b" }),
        target({ target_id: "t3", node_id: "other_block-1", block_type: "other_block" }),
      ],
      blocks,
      schemas,
    );
    // Same node, two ports → one un-indexed label (only one distinct node for the name).
    expect(map.get("t1")?.blockLabel).toBe("Demo Block");
    expect(map.get("t2")?.blockLabel).toBe("Demo Block");
    expect(map.get("t3")?.blockLabel).toBe("Other Block");
  });

  it("marks targets without a materialized output as pending", () => {
    const blocks = [summary("demo_block", "Demo Block")];
    const map = describeReadableTargets(
      [target({ target_id: "t1", latest_output_available: false })],
      blocks,
      schemas,
    );
    expect(map.get("t1")?.pending).toBe(true);
  });
});
