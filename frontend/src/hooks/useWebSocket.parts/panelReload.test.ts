/**
 * ADR-054 spec 1, T-011 — the reload trigger, from the websocket inwards
 * (FR-030, FR-032, SC-005).
 *
 * **What A-007 turned out to be about.** The assumption says the watcher
 * behaviour that suppresses files written by the product itself must be
 * confirmed not to suppress agent-written panel files. It does not: the
 * backend's suppression is keyed on an exact `(path, mtime_ns, size)` signature
 * that SciStudio's own write endpoints register before they write, and an agent
 * writing a file with its own editing tools registers nothing, so the lookup
 * misses and the event is emitted. That is the half A-007 asked about, and it
 * holds.
 *
 * What that leaves for the frontend is this: whatever *reaches* it must reload
 * the panel, and it must do so without consulting who wrote the file. These
 * cover both signals the frontend can receive — a `file.changed` naming a path
 * inside a panel directory, and a `blocks.reloaded` naming no panel at all —
 * and they assert the same reload happens either way.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { handleFileChanged } from "./handleFileChanged";

function fileChanged(path: string, source?: string): WorkflowEventMessage {
  return {
    type: "file.changed",
    block_id: null,
    workflow_id: null,
    data: { path, kind: "modified", version: 3, source, source_id: null },
    timestamp: "2026-09-03T00:00:00Z",
  } as unknown as WorkflowEventMessage;
}

const appendLog = vi.fn();

beforeEach(() => {
  resetAppStore();
  appendLog.mockClear();
});

describe("a panel file change reloads that panel", () => {
  it("bumps the changed panel's counter, and only that panel's", () => {
    handleFileChanged(fileChanged("panels/core.table/index.html"), { appendLog });

    const state = useAppStore.getState();
    expect(state.panelDocumentVersions["core.table"]).toBe(1);
    expect(state.panelDocumentVersions["core.other"]).toBeUndefined();
    // Nothing global moved: one panel changed, so one panel remounts.
    expect(state.panelDocumentEpoch).toBe(0);
  });

  it("fires for a file nobody has open in an editor", () => {
    // The reconcile path below this returns early when no tab matches the
    // path, which is the normal case for a panel: the person saved it from the
    // panel editor, or the agent wrote it. A trigger that only fired for files
    // someone happened to have open would be the half-working reload FR-032
    // exists to rule out.
    expect(useAppStore.getState().tabs).toHaveLength(0);
    handleFileChanged(fileChanged("panels/core.table/panel.json"), { appendLog });
    expect(useAppStore.getState().panelDocumentVersions["core.table"]).toBe(1);
  });

  it("fires the same way whoever the event says wrote the file (FR-032)", () => {
    // A person's save and an agent's write reach this identically; the source
    // is never consulted, because a first-party save is suppressed by the
    // backend before it gets here at all.
    handleFileChanged(fileChanged("panels/core.table/index.html", "agent"), { appendLog });
    handleFileChanged(fileChanged("panels/core.table/index.html", "user"), { appendLog });
    expect(useAppStore.getState().panelDocumentVersions["core.table"]).toBe(2);
  });

  it("leaves every panel alone for a file that belongs to none", () => {
    handleFileChanged(fileChanged("blocks/loader.py"), { appendLog });
    expect(useAppStore.getState().panelDocumentVersions).toEqual({});
    expect(useAppStore.getState().panelDocumentEpoch).toBe(0);
  });
});

describe("a change that names no panel remounts every panel", () => {
  it("bumps the epoch, which every mount reads", () => {
    // `blocks.reloaded` is what a registry rebuild, a package install and a
    // branch switch all arrive as. Any panel on screen may be the one whose
    // document moved, so all of them are remounted.
    useAppStore.getState().notePanelDocumentChanged(null);
    expect(useAppStore.getState().panelDocumentEpoch).toBe(1);
    expect(useAppStore.getState().panelDocumentVersions).toEqual({});
  });
});
