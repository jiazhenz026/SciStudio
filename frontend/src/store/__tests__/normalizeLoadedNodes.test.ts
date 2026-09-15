import { describe, expect, it } from "vitest";

import type { WorkflowNode } from "../../types/api";
import { mergeNodeConfig, normalizeLoadedNodes } from "../workflowSlice.parts/workflowHelpers";

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

describe("interaction memory lives under params (#2412)", () => {
  const memory = { enabled: true, decision: { routes: [1] }, signature: { x: ["a.tif"] } };

  it("folds a flat config whose params hold only the agent-written memory", () => {
    const node = {
      id: "r",
      block_type: "data_router",
      config: { mode: "fast", params: { interactive_memory: memory } },
    } as unknown as WorkflowNode;

    const [out] = normalizeLoadedNodes([node]);
    expect(out.config).toEqual({ params: { mode: "fast", interactive_memory: memory } });
  });

  it("mergeNodeConfig writes memory into params and drops the top-level copy", () => {
    const node = {
      id: "r",
      block_type: "data_router",
      config: {
        interactive_memory: { enabled: true, decision: { old: 1 }, signature: {} },
        params: { mode: "fast" },
      },
    } as unknown as WorkflowNode;

    const cleared = { enabled: true, decision: null, signature: null };
    const out = mergeNodeConfig(node, { interactive_memory: cleared });
    expect(out.config).toEqual({ params: { mode: "fast", interactive_memory: cleared } });
  });

  it("mergeNodeConfig leaves a top-level record alone for unrelated edits", () => {
    const legacy = { enabled: true };
    const node = {
      id: "r",
      block_type: "data_router",
      config: { interactive_memory: legacy, params: {} },
    } as unknown as WorkflowNode;

    expect(mergeNodeConfig(node, { mode: "slow" }).config).toEqual({
      interactive_memory: legacy,
      params: { mode: "slow" },
    });
  });
});
