// #1988 — the grey puzzle used to mean two unrelated things at once:
//
//   1. a REGISTERED block that is none of the six base categories (the backend
//      reports `base_category: "unknown"` for a direct `Block` subclass), and
//   2. a `block_type` that resolved to NOTHING in this environment.
//
// (1) works and must look like an ordinary block; (2) is broken and must keep
// saying so. These tests pin that separation, plus the IO-only name inference
// that lets an unresolved loader still read as a loader.

import { describe, expect, it } from "vitest";

import {
  buildBlockNode,
  computeProblemSeverity,
  inferUnresolvedCategory,
} from "../flowNodeBuilder";
import { categoryVisuals, getCategoryVisual } from "../../nodes/BlockNode.parts/categoryVisuals";
import type { BlockSchemaResponse, BlockSummary, WorkflowNode } from "../../../types/api";
import type { BlockNodeData } from "../../../types/ui";

function build(
  overrides: {
    blockType?: string;
    summary?: BlockSummary;
    schema?: BlockSchemaResponse;
    status?: string;
  } = {},
): BlockNodeData {
  const node = {
    id: "n1",
    block_type: overrides.blockType ?? "spectrum_baseline_block",
    config: {},
  } as unknown as WorkflowNode;

  const built = buildBlockNode({
    node,
    position: { x: 0, y: 0 },
    params: {},
    summary: overrides.summary,
    schema: overrides.schema,
    status: overrides.status ?? "idle",
    errorMessage: undefined,
    errorSummary: undefined,
    callbacks: {},
    label: overrides.blockType ?? "spectrum_baseline_block",
    upstreamOmeFields: undefined,
    selectedNodeId: null,
  } as unknown as Parameters<typeof buildBlockNode>[0]);

  return built.data as BlockNodeData;
}

function summaryWith(base_category: string): BlockSummary {
  return {
    name: "Peak Finder",
    type_name: "peak_finder_block",
    base_category,
    input_ports: [],
    output_ports: [],
  } as unknown as BlockSummary;
}

describe("#1988 — a registered block with no base category", () => {
  it("is NOT treated as unresolved just because base_category is 'unknown'", () => {
    const data = build({ summary: summaryWith("unknown") });
    expect(data.unresolved).toBe(false);
    expect(data.category).toBe("unknown");
  });

  it("is NOT treated as unresolved when base_category comes back empty", () => {
    // An empty string is what an older/partial backend payload carries; the
    // block still resolved, so it must not acquire the broken-node treatment.
    const data = build({ summary: summaryWith("") });
    expect(data.unresolved).toBe(false);
    expect(data.category).toBe("unknown");
  });

  it("carries no problem severity of its own", () => {
    expect(build({ summary: summaryWith("unknown") }).problemSeverity).toBe("none");
  });

  it("gets a real macaron rather than the retired grey puzzle", () => {
    const visual = getCategoryVisual("unknown");
    expect(visual.bg).toBe("#b5c4f2");
    expect(visual.dashed).toBeUndefined();
    // The pre-#1988 grey must not survive anywhere in the palette.
    const greys = Object.values(categoryVisuals).filter((v) => v.bg === "#c9d1d9");
    expect(greys).toEqual([]);
  });

  it("keeps `custom` as an alias for the same visual, not for the broken one", () => {
    expect(getCategoryVisual("custom")).toBe(getCategoryVisual("unknown"));
  });

  it("falls back to the no-category visual for an unrecognised category string", () => {
    expect(getCategoryVisual("totally-made-up").bg).toBe("#b5c4f2");
  });
});

describe("#1988 — a block_type that resolved to nothing", () => {
  it("is flagged unresolved when neither a summary nor a schema came back", () => {
    const data = build();
    expect(data.unresolved).toBe(true);
    expect(data.category).toBe("unresolved");
  });

  it("raises a warning so the canvas says what validate_workflow cannot", () => {
    // validate_workflow's unregistered-type check walks EDGES, and an
    // unresolved node has no ports, so it has no edges and is never reported.
    expect(build().problemSeverity).toBe("warning");
  });

  it("is drawn as a dashed hole rather than a solid body", () => {
    const visual = getCategoryVisual("unresolved");
    expect(visual.dashed).toBe(true);
    // It must not consume one of the category hues.
    const hues = ["io", "process", "code", "app", "ai", "subworkflow", "unknown"];
    expect(hues.map((k) => categoryVisuals[k].bg)).not.toContain(visual.bg);
  });

  it("still lets a runtime error outrank the unresolved warning", () => {
    expect(build({ status: "error" }).problemSeverity).toBe("error");
  });

  it("keeps the raw block_type visible as the node label", () => {
    expect(build({ blockType: "srs_load_block" }).blockType).toBe("srs_load_block");
  });
});

describe("#1988 — IO-only inference from the block_type name", () => {
  it("reads a loader as a loader", () => {
    expect(inferUnresolvedCategory("srs_load_block")).toEqual({
      category: "io",
      iconHint: "folder-input",
    });
  });

  it("reads a saver as a saver", () => {
    expect(inferUnresolvedCategory("save_spectrum_block")).toEqual({
      category: "io",
      iconHint: "folder-output",
    });
  });

  it.each(["read", "import", "open"])("treats '%s' as a load-side IO word", (word) => {
    expect(inferUnresolvedCategory(`${word}_thing_block`).category).toBe("io");
  });

  it.each(["write", "export", "dump"])("treats '%s' as a save-side IO word", (word) => {
    expect(inferUnresolvedCategory(`${word}_thing_block`).iconHint).toBe("folder-output");
  });

  it("matches whole words only, so a substring never fakes an IO block", () => {
    // "payload" contains "load"; "download" contains "load" AND "own".
    expect(inferUnresolvedCategory("payload_block").category).toBe("unresolved");
    expect(inferUnresolvedCategory("reader_block").category).toBe("unresolved");
  });

  it("does not guess beyond IO", () => {
    expect(inferUnresolvedCategory("spectrum_baseline_block").category).toBe("unresolved");
    expect(inferUnresolvedCategory("train_model_block").category).toBe("unresolved");
  });

  it("gives an unresolved loader the IO palette AND the load glyph", () => {
    const data = build({ blockType: "package_load_block" });
    expect(data.category).toBe("io");
    expect(data.uiIconHint).toBe("folder-input");
    expect(getCategoryVisual(data.category, undefined, data.uiIconHint).bg).toBe(
      categoryVisuals.io.bg,
    );
  });

  it("keeps the unresolved FACT even when it borrows the IO palette", () => {
    // This is the #1988 requirement that prettier styling must not erase.
    const data = build({ blockType: "package_load_block" });
    expect(data.unresolved).toBe(true);
    expect(data.problemSeverity).toBe("warning");
  });
});

describe("#1988 — computeProblemSeverity ordering", () => {
  const base = {
    category: "process",
    config: {},
    upstreamOmeFields: undefined,
  };

  it("puts a runtime error above an unresolved block", () => {
    expect(computeProblemSeverity({ ...base, status: "error", unresolved: true })).toBe("error");
  });

  it("reports nothing for an ordinary resolved block", () => {
    expect(computeProblemSeverity({ ...base, status: "idle", unresolved: false })).toBe("none");
  });
});
