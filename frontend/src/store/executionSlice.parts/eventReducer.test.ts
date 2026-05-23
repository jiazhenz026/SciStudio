/**
 * Unit tests for the executionSlice event reducer helpers extracted in
 * #1414 (Wave 3 W3-D). These ensure the per-concern pure helpers
 * preserve the legacy ``consumeEvent`` behavior.
 */
import { describe, expect, it } from "vitest";

import type { LogEntry, WorkflowEventMessage } from "../../types/api";
import {
  extractBlockError,
  maybeAppendErrorLog,
  nextBlockOutputs,
  nextBlockStates,
  nextErrorMaps,
  nextIsRunning,
} from "./eventReducer";

function makeEvent(overrides: Partial<WorkflowEventMessage> = {}): WorkflowEventMessage {
  return {
    type: "block_started",
    block_id: "block-1",
    workflow_id: "wf-1",
    data: {},
    timestamp: "2026-05-22T00:00:00Z",
    ...overrides,
  };
}

describe("eventReducer helpers", () => {
  describe("extractBlockError", () => {
    it("returns isBlockError=false for non-error events", () => {
      const result = extractBlockError(makeEvent({ type: "block_started" }));
      expect(result.isBlockError).toBe(false);
      expect(result.errorText).toBeUndefined();
      expect(result.summaryText).toBeUndefined();
    });

    it("extracts error + summary for block_error", () => {
      const result = extractBlockError(
        makeEvent({
          type: "block_error",
          data: { error: "boom", error_summary: "short" },
        }),
      );
      expect(result.isBlockError).toBe(true);
      expect(result.errorText).toBe("boom");
      expect(result.summaryText).toBe("short");
    });

    it("returns isBlockError=false when block_id missing", () => {
      const result = extractBlockError(
        makeEvent({ type: "block_error", block_id: null, data: { error: "x" } }),
      );
      expect(result.isBlockError).toBe(false);
    });
  });

  describe("nextIsRunning", () => {
    it("flips to true on workflow_started", () => {
      expect(nextIsRunning(makeEvent({ type: "workflow_started" }), false)).toBe(true);
    });
    it("flips to false on workflow_completed", () => {
      expect(nextIsRunning(makeEvent({ type: "workflow_completed" }), true)).toBe(false);
    });
    it("passes through current for other types", () => {
      expect(nextIsRunning(makeEvent({ type: "block_started" }), true)).toBe(true);
      expect(nextIsRunning(makeEvent({ type: "block_finished" }), false)).toBe(false);
    });
  });

  describe("nextBlockStates", () => {
    it("strips block_ prefix and merges into the map", () => {
      const result = nextBlockStates(makeEvent({ type: "block_running" }), {});
      expect(result).toEqual({ "block-1": "running" });
    });
    it("returns current when no block_id", () => {
      const current = { existing: "running" };
      expect(nextBlockStates(makeEvent({ block_id: null }), current)).toBe(current);
    });
  });

  describe("nextBlockOutputs", () => {
    it("merges outputs payload", () => {
      const result = nextBlockOutputs(makeEvent({ data: { outputs: { foo: 1 } } }), {
        other: { bar: 2 },
      });
      expect(result).toEqual({ other: { bar: 2 }, "block-1": { foo: 1 } });
    });
    it("returns current when no outputs", () => {
      const current = { other: { bar: 2 } };
      expect(nextBlockOutputs(makeEvent({ data: {} }), current)).toBe(current);
    });
  });

  describe("nextErrorMaps", () => {
    it("returns existing maps when not a block_error", () => {
      const errors = { e: "x" };
      const summaries = { e: "y" };
      const result = nextErrorMaps(
        makeEvent(),
        { isBlockError: false, errorText: undefined, summaryText: undefined },
        errors,
        summaries,
      );
      expect(result.nextErrors).toBe(errors);
      expect(result.nextSummaries).toBe(summaries);
    });
    it("adds error + summary for block_error", () => {
      const result = nextErrorMaps(
        makeEvent({ type: "block_error" }),
        { isBlockError: true, errorText: "boom", summaryText: "short" },
        {},
        {},
      );
      expect(result.nextErrors).toEqual({ "block-1": "boom" });
      expect(result.nextSummaries).toEqual({ "block-1": "short" });
    });
  });

  describe("maybeAppendErrorLog", () => {
    it("returns appended=false when not a block_error", () => {
      const current: LogEntry[] = [];
      const result = maybeAppendErrorLog(
        makeEvent(),
        { isBlockError: false, errorText: undefined, summaryText: undefined },
        current,
      );
      expect(result.appended).toBe(false);
      expect(result.logEntries).toBe(current);
    });
    it("appends a structured log row for block_error", () => {
      const result = maybeAppendErrorLog(
        makeEvent({ type: "block_error" }),
        { isBlockError: true, errorText: "boom", summaryText: undefined },
        [],
      );
      expect(result.appended).toBe(true);
      expect(result.logEntries).toHaveLength(1);
      expect(result.logEntries[0]).toMatchObject({
        level: "error",
        message: "boom",
        block_id: "block-1",
      });
    });
    it("caps at 400 entries", () => {
      const fill = Array.from({ length: 400 }, (_, i) => ({
        timestamp: `t${i}`,
        level: "info",
        message: `m${i}`,
      })) as LogEntry[];
      const result = maybeAppendErrorLog(
        makeEvent({ type: "block_error" }),
        { isBlockError: true, errorText: "new", summaryText: undefined },
        fill,
      );
      expect(result.logEntries).toHaveLength(400);
      expect(result.logEntries[result.logEntries.length - 1].message).toBe("new");
    });
  });
});
