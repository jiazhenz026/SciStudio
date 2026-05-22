import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { AnnotationNode } from "./AnnotationNode";

afterEach(() => cleanup());

// Minimal wrapper for ReactFlow node component rendering.
function renderNode(
  dataOverrides: Partial<{ text: string; onUpdateText: (t: string) => void }> = {},
  selected = false,
) {
  const props = {
    id: "note-1",
    type: "_annotation",
    data: { text: "Hello world", ...dataOverrides },
    selected,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
  } as Parameters<typeof AnnotationNode>[0];

  return render(
    <ReactFlowProvider>
      <AnnotationNode {...props} />
    </ReactFlowProvider>,
  );
}

describe("AnnotationNode", () => {
  it("renders text content", () => {
    renderNode();
    expect(screen.getByTestId("annotation-text")).toHaveTextContent("Hello world");
  });

  it("applies blue ring when selected", () => {
    renderNode({}, true);
    const container = screen.getByTestId("annotation-node");
    expect(container.className).toContain("ring-2");
  });

  it("does not show textarea in view mode", () => {
    renderNode();
    expect(screen.queryByTestId("annotation-textarea")).toBeNull();
  });

  it("enters edit mode on double-click and shows textarea", async () => {
    const user = userEvent.setup();
    renderNode();
    await user.dblClick(screen.getByTestId("annotation-node"));
    expect(screen.getByTestId("annotation-textarea")).toBeInTheDocument();
  });

  it("calls onUpdateText on blur after editing", async () => {
    const onUpdateText = vi.fn();
    const user = userEvent.setup();
    renderNode({ text: "Original", onUpdateText });

    await user.dblClick(screen.getByTestId("annotation-node"));
    const textarea = screen.getByTestId("annotation-textarea");
    await user.clear(textarea);
    await user.type(textarea, "Updated text");
    await user.tab(); // blur

    expect(onUpdateText).toHaveBeenCalledWith("Updated text");
  });
});
