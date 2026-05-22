import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { GroupNode } from "./GroupNode";

afterEach(() => cleanup());

function renderNode(
  dataOverrides: Partial<{
    title: string;
    note: string;
    color: string;
    onUpdateTitle: (t: string) => void;
    onUpdateNote: (n: string) => void;
  }> = {},
  selected = false,
) {
  const props = {
    id: "group-1",
    type: "_group",
    data: { title: "Preprocessing", note: "Optional note", color: "gray", ...dataOverrides },
    selected,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
  } as Parameters<typeof GroupNode>[0];

  return render(
    <ReactFlowProvider>
      <GroupNode {...props} />
    </ReactFlowProvider>,
  );
}

describe("GroupNode", () => {
  it("renders title text", () => {
    renderNode();
    expect(screen.getByTestId("group-title")).toHaveTextContent("Preprocessing");
  });

  it("renders note text", () => {
    renderNode();
    expect(screen.getByTestId("group-note")).toHaveTextContent("Optional note");
  });

  it("shows dashed border", () => {
    renderNode();
    const container = screen.getByTestId("group-node");
    expect(container.style.border).toContain("dashed");
  });

  it("applies blue-tinted border when selected", () => {
    renderNode({}, true);
    const container = screen.getByTestId("group-node");
    expect(container.style.border).toContain("59, 130, 246");
  });

  it("enters title edit mode on double-click", async () => {
    const user = userEvent.setup();
    renderNode();
    const title = screen.getByTestId("group-title");
    await user.dblClick(title);
    expect(screen.getByTestId("group-title-input")).toBeInTheDocument();
  });

  it("calls onUpdateTitle after editing title", async () => {
    const onUpdateTitle = vi.fn();
    const user = userEvent.setup();
    renderNode({ title: "Old Title", onUpdateTitle });

    await user.dblClick(screen.getByTestId("group-title"));
    const input = screen.getByTestId("group-title-input");
    await user.clear(input);
    await user.type(input, "New Title");
    await user.tab(); // blur

    expect(onUpdateTitle).toHaveBeenCalledWith("New Title");
  });
});
