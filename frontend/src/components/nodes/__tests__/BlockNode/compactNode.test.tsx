// ADR-050 (#1698) — square node geometry + identity-only body.
//
// Covers:
//   - SC-001: the node body is a fixed 104×104 square (width === height) and
//     stays stable across idle / running / warning / error / paused states.
//   - FR-003/FR-004: the node body renders NO config controls, NO status
//     footer, NO inline error text, NO warning chip, NO paused toast.
//   - FR-005: a long block label truncates (two visual lines) without changing
//     geometry, and exposes the full text via the title tooltip.
//   - FR-006: the block-kind category mark renders from data.category.

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { makeSchema, openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

const NODE_SIZE = 104;

function bodyOf(container: HTMLElement): HTMLElement {
  const body = container.querySelector('[data-testid="block-node-body"]') as HTMLElement | null;
  if (!body) throw new Error("block-node-body not found");
  return body;
}

describe("BlockNode — fixed square geometry (SC-001 / FR-001/FR-002)", () => {
  it("renders the body as a 104×104 square with equal width and height", () => {
    const { container } = renderNode({ label: "Square" });
    const body = bodyOf(container);
    expect(body.style.width).toBe(`${NODE_SIZE}px`);
    expect(body.style.height).toBe(`${NODE_SIZE}px`);
    expect(body.style.width).toBe(body.style.height);
  });

  it.each(["idle", "running", "paused", "done", "error", "skipped"])(
    "keeps the 104×104 body stable when status=%s",
    (status) => {
      const { container } = renderNode({ status, errorMessage: "boom", errorSummary: "boom" });
      const body = bodyOf(container);
      expect(body.style.width).toBe(`${NODE_SIZE}px`);
      expect(body.style.height).toBe(`${NODE_SIZE}px`);
    },
  );

  it("keeps the 104×104 body stable when a warning problem severity is present", () => {
    const { container } = renderNode({ status: "done", problemSeverity: "warning" });
    const body = bodyOf(container);
    expect(body.style.width).toBe(`${NODE_SIZE}px`);
    expect(body.style.height).toBe(`${NODE_SIZE}px`);
  });

  it("uses a small border radius (≤ 8px)", () => {
    const { container } = renderNode({});
    const body = bodyOf(container);
    const radius = Number.parseInt(body.style.borderRadius, 10);
    expect(radius).toBeLessThanOrEqual(8);
  });
});

describe("BlockNode — identity-only body (FR-003/FR-004)", () => {
  it("renders no config controls in the node body", () => {
    const { container } = renderNode({
      category: "io",
      config: { path: "/data", core_type: "DataFrame" },
      schema: makeSchema({
        base_category: "io",
        direction: "output",
        config_schema: {
          type: "object",
          properties: {
            path: { type: "string", title: "Path", ui_priority: 0 },
            core_type: {
              type: "string",
              enum: ["DataFrame", "Series"],
              ui_priority: 1,
            },
          },
        },
      }),
    });
    const body = bodyOf(container);
    // No editable config widgets of any kind inside the square body.
    expect(body.querySelector("input")).toBeNull();
    expect(body.querySelector("select")).toBeNull();
    expect(body.querySelector("textarea")).toBeNull();
  });

  it("does not render the format-capability selector in the body", () => {
    renderNode({
      category: "io",
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        format_capabilities: [
          {
            id: "imaging.image.tiff.load",
            direction: "load",
            data_type: "Image",
            format_id: "tiff",
            extensions: [".tif"],
            label: "TIFF",
            block_type: "LoadImage",
            handler: "load",
            is_default: true,
            priority: 0,
            roundtrip_group: null,
            metadata_fidelity: {
              level: "typed_meta",
              typed_meta_reads: [],
              typed_meta_writes: [],
              format_metadata_reads: [],
              format_metadata_writes: [],
              notes: null,
            },
            is_synthesized: false,
            migration_scaffold: false,
          },
        ],
      }),
    });
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("does not render inline error text even when status=error and a message is set", () => {
    renderNode({ status: "error", errorMessage: "Division by zero", errorSummary: "Division by zero" });
    // The verbose error text must not appear as a body text row (it lives in
    // Logs / the status-surface tooltip only).
    expect(screen.queryByText("Division by zero")).toBeNull();
  });

  it("does not render a paused toast / waiting-for-input row in the body", () => {
    renderNode({ status: "paused", category: "app", config: { output_dir: "/out" } });
    expect(screen.queryByText(/waiting for user input/i)).toBeNull();
    expect(screen.queryByText(/\/out/)).toBeNull();
  });
});

describe("BlockNode — label cap (FR-005)", () => {
  it("truncates a long label to two lines and exposes full text via title", () => {
    const longLabel = "A very long block label that should be capped to two visual lines on canvas";
    const { container } = renderNode({ label: longLabel });
    const label = container.querySelector(
      '[data-testid="block-node-label"]',
    ) as HTMLElement | null;
    expect(label).not.toBeNull();
    expect(label?.className).toContain("line-clamp-2");
    expect(label?.getAttribute("title")).toBe(longLabel);
    // Geometry is unchanged by the long label.
    const body = bodyOf(container);
    expect(body.style.width).toBe(`${NODE_SIZE}px`);
    expect(body.style.height).toBe(`${NODE_SIZE}px`);
  });
});

describe("BlockNode — block-kind mark (FR-006)", () => {
  it.each([
    ["io", "📁"],
    ["process", "⚙️"],
    ["code", "💻"],
    ["app", "🖥️"],
    ["ai", "✨"],
    ["subworkflow", "📦"],
  ])("renders the %s category mark", (category, mark) => {
    const { container } = renderNode({ category });
    expect(bodyOf(container).textContent).toContain(mark);
  });

  it("falls back to the custom mark for an unknown category", () => {
    const { container } = renderNode({ category: "totally-unknown" });
    expect(bodyOf(container).textContent).toContain("🧩");
  });
});
