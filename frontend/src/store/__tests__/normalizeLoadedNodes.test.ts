import { describe, expect, it } from "vitest";

import type { WorkflowNode } from "../../types/api";
import { normalizeLoadedNodes } from "../workflowSlice.parts/workflowHelpers";

/**
 * Bug #11: a workflow YAML authored by the agent / by hand stores node config
 * FLAT (`config: { path, method }`), but the GUI reads `node.config.params`.
 * Loaded flat nodes therefore showed empty / schema-default values in the config
 * panel. `normalizeLoadedNodes` wraps flat configs into the canonical
 * `{ params }` shape on load.
 */
describe("normalizeLoadedNodes (#11)", () => {
  it("wraps a flat (agent-authored) node config into { params }", () => {
    const nodes = [
      {
        id: "load",
        block_type: "load_data",
        config: { path: "data/raw/*.txt", core_type: "Spectrum" },
      },
      {
        id: "bl",
        block_type: "spectroscopy.baseline_correction",
        config: { method: "arPLS", lam: 100000 },
      },
    ] as unknown as WorkflowNode[];

    const out = normalizeLoadedNodes(nodes);

    expect(out[0].config.params).toEqual({ path: "data/raw/*.txt", core_type: "Spectrum" });
    expect(out[1].config.params).toEqual({ method: "arPLS", lam: 100000 });
  });

  it("leaves an already-wrapped (GUI-created) node unchanged", () => {
    const node = {
      id: "n1",
      block_type: "load_data",
      config: { params: { path: "x.txt", core_type: "Spectrum" } },
    } as unknown as WorkflowNode;

    const [out] = normalizeLoadedNodes([node]);
    expect(out).toBe(node); // identity preserved (idempotent)
    expect(out.config.params).toEqual({ path: "x.txt", core_type: "Spectrum" });
  });

  it("never reshapes an annotation node (GUI-only params + style)", () => {
    const node = {
      id: "note",
      block_type: "_annotation",
      config: { params: { text: "hi" }, style: { width: 240, height: 120 } },
    } as unknown as WorkflowNode;

    const [out] = normalizeLoadedNodes([node]);
    expect(out).toBe(node);
  });

  it("handles an empty/missing config without throwing", () => {
    const nodes = [
      { id: "a", block_type: "load_data", config: {} },
      { id: "b", block_type: "load_data" },
    ] as unknown as WorkflowNode[];

    const out = normalizeLoadedNodes(nodes);
    expect(out[0].config.params).toEqual({});
    expect(out[1].config.params).toEqual({});
  });
});
