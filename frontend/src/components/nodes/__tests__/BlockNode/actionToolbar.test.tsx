// ADR-050 §2.2 + Addendum 1 §8 (#2033) — floating node action toolbar.
//
// The toolbar carries two buttons: run and delete. It used to carry three.
// The middle one, "Restart block", dispatched `handleRestartBlock`, whose body
// was byte-identical to `handleRunBlock` — same `executeFrom` call, same
// arguments, same dependency array. Two icons and two tooltips for one
// behaviour, with nothing to tell a user they were the same thing.

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { NodeActionToolbar } from "../../BlockNode.parts/NodeActionToolbar";
import { openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("NodeActionToolbar (ADR-050 Addendum 1 §8.1)", () => {
  it("renders exactly two buttons", () => {
    render(<NodeActionToolbar visible={true} onRun={vi.fn()} onDelete={vi.fn()} />);
    const toolbar = screen.getByTestId("node-action-toolbar");
    expect(toolbar.querySelectorAll("button")).toHaveLength(2);
  });

  it("exposes Run and Remove, and no Restart", () => {
    render(<NodeActionToolbar visible={true} onRun={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByLabelText("Run block")).toBeTruthy();
    expect(screen.getByLabelText("Remove block")).toBeTruthy();
    expect(screen.queryByLabelText("Restart block")).toBeNull();
  });

  it("Run fires onRun and stops the click from reaching the node", () => {
    const onRun = vi.fn();
    const onNodeClick = vi.fn();
    render(
      <div onClick={onNodeClick}>
        <NodeActionToolbar visible={true} onRun={onRun} onDelete={vi.fn()} />
      </div>,
    );
    fireEvent.click(screen.getByLabelText("Run block"));
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onNodeClick).not.toHaveBeenCalled();
  });

  it("Remove fires onDelete", () => {
    const onDelete = vi.fn();
    render(<NodeActionToolbar visible={true} onRun={vi.fn()} onDelete={onDelete} />);
    fireEvent.click(screen.getByLabelText("Remove block"));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("is not clickable while hidden (§2.2 pointer-events toggle)", () => {
    render(<NodeActionToolbar visible={false} onRun={vi.fn()} onDelete={vi.fn()} />);
    const toolbar = screen.getByTestId("node-action-toolbar");
    expect(toolbar.className).toContain("pointer-events-none");
    expect(toolbar.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("BlockNode wiring", () => {
  it("renders the two-button toolbar on the node", () => {
    renderNode({ onRun: vi.fn(), onDelete: vi.fn() });
    const toolbar = screen.getByTestId("node-action-toolbar");
    expect(toolbar.querySelectorAll("button")).toHaveLength(2);
    expect(screen.queryByLabelText("Restart block")).toBeNull();
  });
});
