// ADR-044 §3 (locked contract item 4) — subworkflow exposed-port connectability.
//
// SubWorkflowNode reuses the same PortHandles as BlockNode and never passes
// isConnectable=false, so its exposed-port handles (Handle id == port name) are
// connectable. This test asserts the connect path that PortHandles feeds —
// `useCanvasHandlers.handleConnect` — turns a Connection whose handles are the
// exposed port names into the persisted colon-ref form
// `"<subworkflowNodeId>:<portName>"` for both source and target endpoints.

import type { Connection } from "@xyflow/react";
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useCanvasHandlers } from "../useCanvasHandlers";

function renderConnectHandler(onConnect: (edge: { source: string; target: string }) => void) {
  // useCanvasHandlers only reads `reactFlow` lazily (in drop/resize handlers),
  // not in handleConnect, so a minimal stub suffices for this path.
  const reactFlow = {} as Parameters<typeof useCanvasHandlers>[0]["reactFlow"];
  const { result } = renderHook(() =>
    useCanvasHandlers({
      reactFlow,
      edges: [],
      onAddNode: vi.fn(),
      onConnect: async (edge) => onConnect(edge),
      onDeleteEdge: vi.fn(),
      onDeleteNode: vi.fn(),
      onSelectNode: vi.fn(),
      onUpdateNodePosition: vi.fn(),
      setDragPositions: vi.fn(),
      setDragSizes: vi.fn(),
    }),
  );
  return result;
}

describe("ADR-044 subworkflow port connect path", () => {
  it("persists an edge from a subworkflow exposed port as nodeId:portName", async () => {
    const onConnect = vi.fn();
    const result = renderConnectHandler(onConnect);

    // A drag from a subworkflow node's `report` output handle to a downstream
    // block's `raw_in` input handle. Handle ids EQUAL the exposed port names.
    const connection: Connection = {
      source: "sw1",
      sourceHandle: "report",
      target: "qc",
      targetHandle: "raw_in",
    };

    await result.current.handleConnect(connection);

    expect(onConnect).toHaveBeenCalledWith({ source: "sw1:report", target: "qc:raw_in" });
  });

  it("ignores a connection with a missing handle (cannot form a colon ref)", async () => {
    const onConnect = vi.fn();
    const result = renderConnectHandler(onConnect);

    await result.current.handleConnect({
      source: "sw1",
      sourceHandle: null,
      target: "qc",
      targetHandle: "raw_in",
    } as Connection);

    expect(onConnect).not.toHaveBeenCalled();
  });
});
