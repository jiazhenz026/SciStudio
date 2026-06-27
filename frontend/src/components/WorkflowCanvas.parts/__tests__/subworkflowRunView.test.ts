// ADR-044 — run-view helpers for collapsed/expanded subworkflow run status.
import { describe, expect, it } from "vitest";

import type { WorkflowNode } from "../../../types/api";
import { aggregateSubworkflowStatus, buildScopedBlockOutputs } from "../subworkflowRunView";

function swNode(id: string, outputs: string[]): WorkflowNode {
  return {
    id,
    block_type: "subworkflow_block",
    config: { ref: { path: "subworkflows/child.yaml" } },
    resolved_ports: {
      inputs: [],
      outputs: outputs.map((name) => ({ name, accepted_types: [] })),
      broken: false,
      ref_path: "subworkflows/child.yaml",
    },
  } as WorkflowNode;
}

describe("aggregateSubworkflowStatus", () => {
  const prefix = "sw1__";

  it("returns idle when no inner block has reported", () => {
    expect(aggregateSubworkflowStatus({ other__x: "running" }, prefix)).toBe("idle");
  });

  it("returns running while any inner block is running", () => {
    const states = { sw1__a: "done", sw1__b: "running", sw1__c: "idle" };
    expect(aggregateSubworkflowStatus(states, prefix)).toBe("running");
  });

  it("returns running for partial progress (some done, none running yet)", () => {
    expect(aggregateSubworkflowStatus({ sw1__a: "done", sw1__b: "idle" }, prefix)).toBe("running");
  });

  it("returns error when any inner block errored, over a running sibling", () => {
    expect(aggregateSubworkflowStatus({ sw1__a: "running", sw1__b: "error" }, prefix)).toBe(
      "error",
    );
  });

  it("returns done only when every observed inner block is terminal-done", () => {
    expect(aggregateSubworkflowStatus({ sw1__a: "done", sw1__b: "completed" }, prefix)).toBe(
      "done",
    );
  });

  it("ignores keys outside the prefix (nesting isolation)", () => {
    // sw1__sw2__x belongs to a nested child; the sw1 roll-up still sees it
    // (it starts with sw1__) but an unrelated other__y is excluded.
    const states = { sw1__sw2__x: "running", other__y: "error" };
    expect(aggregateSubworkflowStatus(states, prefix)).toBe("running");
  });
});

describe("buildScopedBlockOutputs", () => {
  it("maps a subworkflow node's exposed outputs to inner block outputs", () => {
    const nodes = [swNode("sw1", ["d_cen.features", "corr.combined"])];
    const raw = {
      sw1__d_cen: { features: { ref: "a" } },
      sw1__corr: { combined: { ref: "b" } },
    };
    const scoped = buildScopedBlockOutputs(nodes, raw, "");
    expect(scoped.sw1).toEqual({
      "d_cen.features": { ref: "a" },
      "corr.combined": { ref: "b" },
    });
  });

  it("omits exposed outputs whose inner block has not produced data", () => {
    const nodes = [swNode("sw1", ["d_cen.features"])];
    const scoped = buildScopedBlockOutputs(nodes, {}, "");
    expect(scoped.sw1).toBeUndefined();
  });

  it("aliases a child node's prefixed run outputs under its own id (expanded view)", () => {
    const child: WorkflowNode = { id: "d_bl", block_type: "spectroscopy.baseline", config: {} };
    const raw = { sw1__d_bl: { baseline: { ref: "z" } } };
    const scoped = buildScopedBlockOutputs([child], raw, "sw1__");
    expect(scoped.d_bl).toEqual({ baseline: { ref: "z" } });
  });

  it("composes the prefix for a subworkflow node inside an expanded child canvas", () => {
    const nodes = [swNode("sw2", ["corr.combined"])];
    const raw = { sw1__sw2__corr: { combined: { ref: "n" } } };
    const scoped = buildScopedBlockOutputs(nodes, raw, "sw1__");
    expect(scoped.sw2).toEqual({ "corr.combined": { ref: "n" } });
  });

  it("leaves the raw map untouched for a top-level canvas with no subworkflow", () => {
    const nodes: WorkflowNode[] = [{ id: "a", block_type: "x", config: {} }];
    const raw = { a: { out: 1 } };
    expect(buildScopedBlockOutputs(nodes, raw, "")).toEqual({ a: { out: 1 } });
  });
});
