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
        input_signature: { input_1: ["spectrum_01.txt", "spectrum_02.txt"] },
      },
      timestamp: "2026-06-26T00:00:00Z",
    });

    expect(result).not.toBeNull();
    expect(result?.blockId).toBe("node-a");
    expect(result?.blockType).toBe("DataRouter");
    // ADR-051 Addendum 1: the engine's input fingerprint is captured for memory.
    expect(result?.inputSignature).toEqual({
      input_1: ["spectrum_01.txt", "spectrum_02.txt"],
    });
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

  // ADR-054 spec 1 D-020 — the descriptor the paused block's panel mounts from.
  //
  // The manifest above is the retired ES-module shape: no capability, no
  // document URL, no asset base, no read limits, so `validatePanelDescriptor`
  // refuses it (D-016.3) and the reader gets the host's error surface instead of
  // the panel. The engine emits a descriptor beside it
  // (`engine/scheduler/_dispatch.py`, pinned by
  // `tests/engine/test_interactive_panel_descriptor.py`); this is the one line
  // that carries it from the wire into the store the host reads.
  it("lifts the panel descriptor the backend resolved for the block", () => {
    const descriptor = {
      panel_id: "core.interactive.data_router",
      display_name: "core.interactive.data_router",
      api_version: "1",
      accepted_api_version: "1",
      capability: "producing",
      document_url: "/api/panels/assets/core.interactive.data_router/index.html",
      asset_base_url: "/api/panels/assets/core.interactive.data_router/",
      read_limits: { max_rows: 500, max_bytes: 1_000_000 },
    };

    const result = capture({
      type: "interactive_prompt",
      block_id: "node-a",
      workflow_id: "wf-1",
      data: {
        block_type: "DataRouter",
        panel_manifest: { panel_id: "core.interactive.data_router", version: "1" },
        panel_descriptor: descriptor,
        panel_payload: {},
      },
      timestamp: "t",
    });

    expect(result?.panelDescriptor).toEqual(descriptor);
    // FR-022: the retired shape rides along for the migration rather than being
    // dropped, so an unmigrated reader of `panel_manifest` keeps working.
    expect(result?.panelManifest?.panel_id).toBe("core.interactive.data_router");
  });

  it("reports no descriptor rather than inventing one", () => {
    // A prompt without a descriptor is a backend defect, and the host says so
    // on its own error surface — with Cancel reachable, because a person must
    // never be stuck on a paused block with no exit (#2195).
    const result = capture({
      type: "interactive_prompt",
      block_id: "b",
      workflow_id: "w",
      data: { block_type: "X", panel_manifest: { panel_id: "myproj.foo" } },
      timestamp: "t",
    });

    expect(result?.panelDescriptor).toBeNull();
  });
});
