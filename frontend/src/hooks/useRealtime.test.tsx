import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import { useLogStream } from "./useSSE";
import { useWorkflowWebSocket } from "./useWebSocket";

class MockWebSocket {
  static instance: MockWebSocket | null = null;
  static OPEN = 1;
  readyState = MockWebSocket.OPEN;
  send = vi.fn();
  onopen?: () => void;
  onclose?: () => void;
  onerror?: () => void;
  onmessage?: (event: MessageEvent<string>) => void;

  constructor() {
    MockWebSocket.instance = this;
    queueMicrotask(() => this.onopen?.());
  }

  close() {
    this.onclose?.();
  }
}

class MockEventSource {
  static instance: MockEventSource | null = null;
  onopen?: () => void;
  onerror?: () => void;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();

  constructor() {
    MockEventSource.instance = this;
    queueMicrotask(() => this.onopen?.());
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }

  close() {}
}

function Harness() {
  useWorkflowWebSocket(true);
  useLogStream("wf-1", null);
  const state = useAppStore((store) => store.blockStates["node-1"] ?? "none");
  const logs = useAppStore((store) => store.logEntries.length);
  return (
    <div>
      <span data-testid="state">{state}</span>
      <span data-testid="logs">{logs}</span>
    </div>
  );
}

describe("realtime hooks", () => {
  beforeEach(() => {
    resetAppStore();
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("updates store state from websocket and SSE events", async () => {
    // #2362: the node-keyed maps are held per workflow and projected onto the
    // one on screen, so the run the harness watches has to be the open one —
    // which is what it is in the product.
    useAppStore.setState({ workflowId: "wf-1" });
    render(<Harness />);

    MockWebSocket.instance?.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          type: "block_done",
          block_id: "node-1",
          workflow_id: "wf-1",
          data: { outputs: { output: { data_ref: "data-1" } } },
          timestamp: new Date().toISOString(),
        }),
      }),
    );

    MockEventSource.instance?.listeners.get("log")?.(
      new MessageEvent("message", {
        data: JSON.stringify({
          timestamp: new Date().toISOString(),
          level: "info",
          message: "workflow started",
          workflow_id: "wf-1",
        }),
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("state")).toHaveTextContent("done");
      expect(screen.getByTestId("logs")).toHaveTextContent("1");
    });
  });
});
