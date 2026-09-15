// Canvas node hover-detail popover behavior (#1887).
//
// Hovering a placed block node opens the shared BlockDetailPopover after a
// ~400ms dwell, showing the block's description and typed ports — mirroring the
// palette hover detail. It dismisses on leave and no-ops without a summary.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";

import type { BlockSummary } from "../../../../types/api";
import { POPOVER_CLOSE_DELAY_MS } from "../../../palette/hoverPopover";
import { NODE_DETAIL_OPEN_DELAY_MS } from "../../BlockNode.parts/nodeDetailAnchor";
import { makePort, openNativeDialogMock, renderNode } from "./test-utils";

function makeSummary(overrides: Partial<BlockSummary> = {}): BlockSummary {
  return {
    name: "Cellpose Segment",
    type_name: "cellpose_segment",
    base_category: "ai",
    subcategory: "",
    description: "Run Cellpose model on an image to produce instance masks.",
    version: "1.0",
    input_ports: [makePort("image", "input", ["Image"])],
    output_ports: [makePort("masks", "output", ["Mask"])],
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — hover detail popover (#1887)", () => {
  it("opens the detail popover after the dwell, with description and typed ports", () => {
    renderNode({ summary: makeSummary() });

    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId("block-node-shell"));
    act(() => {
      vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS);
    });

    const popover = screen.getByTestId("block-detail-popover");
    expect(
      within(popover).getByText("Run Cellpose model on an image to produce instance masks."),
    ).toBeInTheDocument();
    expect(within(popover).getByText("Image")).toBeInTheDocument();
    expect(within(popover).getByText("Mask")).toBeInTheDocument();
  });

  it("does not open before the dwell elapses", () => {
    renderNode({ summary: makeSummary() });

    fireEvent.mouseEnter(screen.getByTestId("block-node-shell"));
    act(() => {
      vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS - 50);
    });

    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("dismisses the popover when the cursor leaves the node", () => {
    renderNode({ summary: makeSummary() });

    const shell = screen.getByTestId("block-node-shell");
    fireEvent.mouseEnter(shell);
    act(() => {
      vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS);
    });
    expect(screen.getByTestId("block-detail-popover")).toBeInTheDocument();

    fireEvent.mouseLeave(shell);
    act(() => vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS));
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("survives pointer transit and dwell inside, then closes after leaving the card", () => {
    const action = vi.fn();
    renderNode({
      summary: makeSummary(),
      detailActions: <button onClick={action}>New MiniApp</button>,
    });
    const shell = screen.getByTestId("block-node-shell");
    fireEvent.mouseEnter(shell);
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    const popover = screen.getByTestId("block-detail-popover");
    expect(popover.className).not.toContain("pointer-events-none");
    fireEvent.mouseLeave(shell);
    act(() => vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS - 1));
    fireEvent.mouseEnter(popover);
    act(() => vi.advanceTimersByTime(1000));
    expect(popover).toBeInTheDocument();
    fireEvent.mouseLeave(popover);
    act(() => vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS));
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("allows clicking a popover action without starting node drag and closes after selection", () => {
    const action = vi.fn();
    renderNode({
      summary: makeSummary(),
      detailActions: <button onClick={action}>Edit block</button>,
    });
    fireEvent.mouseEnter(screen.getByTestId("block-node-shell"));
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    const button = screen.getByRole("button", { name: "Edit block" });
    fireEvent.mouseDown(button);
    expect(screen.getByTestId("block-detail-popover")).toBeInTheDocument();
    fireEvent.click(button);
    expect(action).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("closes on Escape and on node mouse-down before dragging", () => {
    renderNode({ summary: makeSummary(), detailActions: <button>Edit block</button> });
    const shell = screen.getByTestId("block-node-shell");
    fireEvent.mouseEnter(shell);
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
    fireEvent.mouseLeave(shell);
    fireEvent.mouseEnter(shell);
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    fireEvent.mouseDown(shell);
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("closes when the canvas viewport changes or a pointer starts outside the node", () => {
    const { flowStore } = renderNode({ summary: makeSummary() });
    const shell = screen.getByTestId("block-node-shell");
    fireEvent.mouseEnter(shell);
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    act(() => flowStore().setState({ transform: [20, 30, 1.5] }));
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
    fireEvent.mouseLeave(shell);
    fireEvent.mouseEnter(shell);
    act(() => vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("no-ops when the block summary is unavailable", () => {
    renderNode({ summary: undefined });

    fireEvent.mouseEnter(screen.getByTestId("block-node-shell"));
    act(() => {
      vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS);
    });

    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();
  });

  it("portals the popover outside the node subtree (escapes ReactFlow transforms)", () => {
    // #1887 P2: a position:fixed popover under ReactFlow's transformed viewport
    // would be placed in the transformed coordinate space and drift after
    // pan/zoom. Portalling to <body> keeps it in the real viewport space that
    // getBoundingClientRect() (used for the anchor) reports in.
    const { container } = renderNode({ summary: makeSummary() });

    fireEvent.mouseEnter(screen.getByTestId("block-node-shell"));
    act(() => {
      vi.advanceTimersByTime(NODE_DETAIL_OPEN_DELAY_MS);
    });

    const popover = screen.getByTestId("block-detail-popover");
    // Not rendered inside the node's own subtree...
    expect(container.querySelector('[data-testid="block-detail-popover"]')).toBeNull();
    // ...but mounted on document.body via the portal.
    expect(document.body.contains(popover)).toBe(true);
  });
});
