/**
 * ADR-051 FR-007/FR-015: handleInteractivePrompt lifts the panel manifest and
 * the nested panel payload from the interactive_prompt event so the frontend
 * resolves the window from the manifest (not a hardcoded blockType branch).
 */
import { describe, expect, it } from "vitest";

import type { InteractivePrompt } from "../../store/types";
import type { WorkflowEventMessage } from "../../types/api";
import { handleInteractivePrompt } from "./handleLifecycle";

function capture(payload: WorkflowEventMessage): InteractivePrompt | null {
  let captured: InteractivePrompt | null = null;
  handleInteractivePrompt(payload, {
    setInteractivePrompt: (p) => {
      captured = p;
    },
  });
  return captured;
}

describe("handleInteractivePrompt (ADR-051)", () => {
  it("lifts the panel manifest and nests the panel payload", () => {
    const result = capture({
      type: "interactive_prompt",
      block_id: "node-a",
      workflow_id: "wf-1",
      data: {
        workflow_id: "wf-1",
        block_type: "DataRouter",
        panel_manifest: { panel_id: "core.interactive.data_router", version: "1" },
        panel_payload: { input_ports: ["x"], output_ports: ["y"], items_per_port: {} },
      },
      timestamp: "2026-06-26T00:00:00Z",
    });

    expect(result).not.toBeNull();
    expect(result?.blockId).toBe("node-a");
    expect(result?.blockType).toBe("DataRouter");
    // The prompt's own workflow id is lifted so confirm/cancel can run-scope it
    // (not the store's active workflow id) — codex P1.
    expect(result?.workflowId).toBe("wf-1");
    expect(result?.panelManifest?.panel_id).toBe("core.interactive.data_router");
    expect(result?.panelPayload).toEqual({
      input_ports: ["x"],
      output_ports: ["y"],
      items_per_port: {},
    });
    // The payload is nested, not spread into the top-level data envelope.
    expect((result?.data as Record<string, unknown>).input_ports).toBeUndefined();
  });

  it("tolerates a missing manifest and payload", () => {
    const result = capture({
      type: "interactive_prompt",
      block_id: "b",
      workflow_id: "w",
      data: { block_type: "X" },
      timestamp: "t",
    });

    expect(result?.panelManifest).toBeNull();
    expect(result?.panelPayload).toEqual({});
    expect(result?.workflowId).toBe("w");
  });
});
