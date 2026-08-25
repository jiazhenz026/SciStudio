// #2151 — drop-position anchoring.
//
// A React Flow node position is the node's top-left corner, so dropping a
// palette block at the raw cursor point lands the block down-right of the
// mouse. `useCanvasHandlers.handleDrop` re-anchors the drop on the fixed
// square body's centre (ADR-050 §2.1, NODE_SIZE), so the block lands centred
// under the cursor.

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NODE_SIZE } from "../../nodes/BlockNode.parts/nodeGeometry";
import type { BlockSummary } from "../../../types/api";
import { useCanvasHandlers } from "../useCanvasHandlers";

const block: BlockSummary = {
  name: "Cellpose Segment",
  type_name: "imaging.cellpose_segment",
  base_category: "process",
  subcategory: "",
  description: "",
  version: "0.1.0",
  input_ports: [],
  output_ports: [],
};

function renderDropHandler() {
  const onAddNode = vi.fn();
  // The cursor maps to a known flow point; the handler must re-anchor from
  // there, so the stub makes the before/after difference observable.
  const reactFlow = {
    screenToFlowPosition: ({ x, y }: { x: number; y: number }) => ({ x: x - 40, y: y - 100 }),
  } as unknown as Parameters<typeof useCanvasHandlers>[0]["reactFlow"];
  const { result } = renderHook(() =>
    useCanvasHandlers({
      reactFlow,
      edges: [],
      onAddNode,
      onConnect: vi.fn(),
      onDeleteEdge: vi.fn(),
      onDeleteNode: vi.fn(),
      onSelectNode: vi.fn(),
      onUpdateNodePosition: vi.fn(),
      setDragPositions: vi.fn(),
      setDragSizes: vi.fn(),
    }),
  );
  return { onAddNode, result };
}

function dropEvent(payload: unknown, client = { x: 500, y: 300 }) {
  return {
    preventDefault: vi.fn(),
    clientX: client.x,
    clientY: client.y,
    dataTransfer: { getData: () => (payload == null ? "" : JSON.stringify(payload)) },
  } as unknown as React.DragEvent<HTMLDivElement>;
}

describe("canvas drop position (#2151)", () => {
  it("centres the block's square body on the cursor, not its top-left corner", () => {
    const { onAddNode, result } = renderDropHandler();

    result.current.handleDrop(dropEvent(block, { x: 500, y: 300 }));

    // screenToFlowPosition maps (500, 300) -> (460, 200); the block's centre
    // must sit on that point, so the top-left moves up-left by half the body.
    expect(onAddNode).toHaveBeenCalledWith(
      expect.objectContaining({ type_name: block.type_name }),
      { x: 460 - NODE_SIZE / 2, y: 200 - NODE_SIZE / 2 },
      undefined,
    );
  });

  it("keeps the default-direction envelope while re-anchoring", () => {
    const { onAddNode, result } = renderDropHandler();

    result.current.handleDrop(dropEvent({ ...block, _default_direction: "input" }));

    expect(onAddNode).toHaveBeenCalledWith(
      expect.objectContaining({ type_name: block.type_name }),
      { x: 460 - NODE_SIZE / 2, y: 200 - NODE_SIZE / 2 },
      { direction: "input" },
    );
  });

  it("ignores a drop without the block payload", () => {
    const { onAddNode, result } = renderDropHandler();

    result.current.handleDrop(dropEvent(null));

    expect(onAddNode).not.toHaveBeenCalled();
  });
});
