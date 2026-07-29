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
  nextBlockRunStarts,
  nextBlockStates,
  nextErrorMaps,
  nextIsRunning,
  resolveRunStartedAt,
  summarizeErrorText,
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

    it("derives a one-line summary from a traceback when no summary is provided", () => {
      const traceback = [
        "Traceback (most recent call last):",
        '  File "worker.py", line 1, in main',
        "ValueError: SaveData cannot infer an output filename.",
      ].join("\n");
      const result = extractBlockError(
        makeEvent({
          type: "block_error",
          data: { error: traceback },
        }),
      );
      expect(result.errorText).toBe(traceback);
      expect(result.summaryText).toBe("SaveData cannot infer an output filename.");
    });

    it("returns isBlockError=false when block_id missing", () => {
      const result = extractBlockError(
        makeEvent({ type: "block_error", block_id: null, data: { error: "x" } }),
      );
      expect(result.isBlockError).toBe(false);
    });
  });

  describe("summarizeErrorText", () => {
    it("keeps the final exception message concise", () => {
      expect(summarizeErrorText("Traceback\nRuntimeError: Something failed")).toBe(
        "Something failed",
      );
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

  // #1974 — the node's elapsed counter is anchored to the engine's
  // block_running timestamp and must vanish the moment the block stops.
  describe("resolveRunStartedAt", () => {
    it("uses the engine event timestamp as the run start", () => {
      const now = Date.parse("2026-05-22T00:00:30Z");
      expect(resolveRunStartedAt("2026-05-22T00:00:00Z", now)).toBe(
        Date.parse("2026-05-22T00:00:00Z"),
      );
    });

    it("falls back to the client clock when the timestamp is missing or unparsable", () => {
      const now = 1_700_000_000_000;
      expect(resolveRunStartedAt(undefined, now)).toBe(now);
      expect(resolveRunStartedAt("not-a-timestamp", now)).toBe(now);
    });

    it("falls back to the client clock when the engine clock reads ahead", () => {
      const now = Date.parse("2026-05-22T00:00:00Z");
      expect(resolveRunStartedAt("2026-05-22T01:00:00Z", now)).toBe(now);
    });
  });

  describe("nextBlockRunStarts", () => {
    it("stamps the run start from the block_running event timestamp", () => {
      const now = Date.parse("2026-05-22T00:00:05Z");
      const result = nextBlockRunStarts(makeEvent({ type: "block_running" }), {}, now);
      expect(result).toEqual({ "block-1": Date.parse("2026-05-22T00:00:00Z") });
    });

    it("re-stamps the start when the block enters running again", () => {
      const now = Date.parse("2026-05-22T00:10:00Z");
      const result = nextBlockRunStarts(
        makeEvent({ type: "block_running", timestamp: "2026-05-22T00:09:00Z" }),
        { "block-1": Date.parse("2026-05-22T00:00:00Z") },
        now,
      );
      expect(result).toEqual({ "block-1": Date.parse("2026-05-22T00:09:00Z") });
    });

    it("drops the entry when the block finishes so no duration is retained", () => {
      const started = { "block-1": Date.parse("2026-05-22T00:00:00Z") };
      for (const type of [
        "block_done",
        "block_error",
        "block_cancelled",
        "block_skipped",
        "block_paused",
      ]) {
        expect(nextBlockRunStarts(makeEvent({ type }), started)).toEqual({});
      }
    });

    it("leaves other blocks' run starts untouched", () => {
      const started = { "block-2": 1_700_000_000_000 };
      expect(nextBlockRunStarts(makeEvent({ type: "block_done" }), started)).toBe(started);
      expect(
        nextBlockRunStarts(makeEvent({ type: "block_done", block_id: "block-2" }), started),
      ).toEqual({});
    });

    it("returns current when the event carries no block_id", () => {
      const current = { "block-1": 1_700_000_000_000 };
      expect(
        nextBlockRunStarts(makeEvent({ type: "workflow_completed", block_id: null }), current),
      ).toBe(current);
      expect(nextBlockRunStarts(makeEvent({ block_id: null }), current)).toBe(current);
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
        { isBlockError: true, errorText: "RuntimeError: boom", summaryText: "boom" },
        [],
      );
      expect(result.appended).toBe(true);
      expect(result.logEntries).toHaveLength(1);
      expect(result.logEntries[0]).toMatchObject({
        level: "error",
        message: "boom",
        details: "RuntimeError: boom",
        block_id: "block-1",
      });
    });
    it("stores the full traceback as expandable log details", () => {
      const traceback = [
        "Traceback (most recent call last):",
        '  File "worker.py", line 1, in main',
        "ValueError: Choose a new output path.",
      ].join("\n");
      const result = maybeAppendErrorLog(
        makeEvent({ type: "block_error" }),
        { isBlockError: true, errorText: traceback, summaryText: "Choose a new output path." },
        [],
      );
      expect(result.logEntries[0]).toMatchObject({
        message: "Choose a new output path.",
        details: traceback,
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
        { isBlockError: true, errorText: "new", summaryText: "new" },
        fill,
      );
      expect(result.logEntries).toHaveLength(400);
      expect(result.logEntries[result.logEntries.length - 1].message).toBe("new");
    });
  });
});
