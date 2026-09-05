/**
 * ADR-054 spec 5 FR-001, frontend half — the wire body, per mode.
 *
 * The body is the whole subject. Issue #2237 tracks the failure this suite is
 * written against: a hand-written fixture that agrees with the frontend while
 * both disagree with the server. So the assertions here are on the exact JSON
 * that leaves `postWorkspaceFocus`, field for field, and the manager asserts
 * the same shape against the backend's Pydantic model at integration.
 *
 * Three properties of the backend contract are pinned as well as the shapes:
 * `workflow_id` goes out in every mode; `postActiveWorkflowContext` omits the
 * `focus` key rather than sending `null`, because the backend tells those
 * apart; and the same focus is not reported twice.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiCore from "../lib/api/core";
import { resetAppStore } from "../testUtils";
import { useAppStore } from "../store";
import type { AppStore, ExploreTab, FileTab, TabState, WorkflowTab } from "../store/types";

import {
  deriveWorkspaceFocus,
  reportWorkspaceFocus,
  resetWorkspaceFocusReporter,
  workspaceFocusKey,
} from "./workspaceFocus";

const apiFetch = vi.fn();
vi.mock("../lib/api/core", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiCore>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

const PATH = "explore/analysis.ipynb";

function exploreTab(overrides: Partial<ExploreTab> = {}): ExploreTab {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: "sess-1",
    displayName: "analysis.ipynb",
    mode: "session",
    boundRunId: "run-7",
    pauseNodeId: null,
    notebookVisible: true,
    ...overrides,
  };
}

function workflowTab(): WorkflowTab {
  return { kind: "workflow", id: "tab-wf", workflowId: "wf-1" } as WorkflowTab;
}

function fileTab(): FileTab {
  return { kind: "file", id: "file:a.py", filePath: "a.py" } as FileTab;
}

/** The body of the last POST to the active-context channel. */
function lastBody(): Record<string, unknown> {
  const calls = apiFetch.mock.calls;
  const call = calls[calls.length - 1];
  expect(call?.[0]).toBe("/api/ai/active-context");
  return JSON.parse((call?.[1] as { body: string }).body) as Record<string, unknown>;
}

/**
 * Only the posts that state a focus.
 *
 * The active-workflow sync rides the same route and the same `apiFetch`, and
 * the store subscriber fires both, so counting raw calls would count it too.
 * A body with a `focus` key is one of ours - which is the same distinction the
 * backend makes with `model_fields_set`.
 */
function focusBodies(): Record<string, unknown>[] {
  return apiFetch.mock.calls
    .map((call) => JSON.parse((call[1] as { body: string }).body) as Record<string, unknown>)
    .filter((body) => "focus" in body);
}

beforeEach(() => {
  resetAppStore();
  resetWorkspaceFocusReporter();
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ workflow_id: null });
});

describe("the body per mode", () => {
  it("reports canvas with the workflow the editor has open", () => {
    const focus = deriveWorkspaceFocus([workflowTab()], "tab-wf", "wf-1", null);
    expect(focus).toEqual({ mode: "canvas", workflow_id: "wf-1" });
  });

  it("reports explore with the session path, the bound run, and the current cell", () => {
    const tab = exploreTab();
    const focus = deriveWorkspaceFocus([tab], tab.id, "wf-1", "cell-3");
    expect(focus).toEqual({
      mode: "explore",
      workflow_id: "wf-1",
      session_path: PATH,
      bound_run_id: "run-7",
      current_cell_id: "cell-3",
    });
  });

  it("reports pause with the paused node and its run", () => {
    const tab = exploreTab({ mode: "pause", pauseNodeId: "node-9", boundRunId: "run-9" });
    const focus = deriveWorkspaceFocus([tab], tab.id, "wf-1", null);
    expect(focus).toEqual({
      mode: "pause",
      workflow_id: "wf-1",
      paused_node_id: "node-9",
      paused_run_id: "run-9",
      session_path: PATH,
    });
  });

  it("sends the workflow id in every mode", () => {
    // Switching to an Explore tab does not mean the person closed their
    // workflow, and an agent told "explore" with no workflow would think so.
    const tab = exploreTab();
    for (const state of [
      deriveWorkspaceFocus([workflowTab()], "tab-wf", "wf-1", null),
      deriveWorkspaceFocus([tab], tab.id, "wf-1", null),
      deriveWorkspaceFocus([exploreTab({ mode: "pause" })], `explore:${PATH}`, "wf-1", null),
    ]) {
      expect(state.workflow_id).toBe("wf-1");
    }
  });

  it("calls a file tab and a preview tab the canvas, not a fourth mode", () => {
    expect(deriveWorkspaceFocus([fileTab()], "file:a.py", "wf-1", null).mode).toBe("canvas");
    expect(deriveWorkspaceFocus([], null, null, null)).toEqual({
      mode: "canvas",
      workflow_id: null,
    });
  });
});

describe("what goes on the wire", () => {
  function stateWith(tabs: TabState[], activeTabId: string | null, workflowId: string | null) {
    useAppStore.setState({ tabs, activeTabId, workflowId });
    return useAppStore.getState() as AppStore;
  }

  it("posts to the existing active-context channel, not a new endpoint", () => {
    reportWorkspaceFocus(stateWith([workflowTab()], "tab-wf", "wf-1"));
    expect(focusBodies()).toHaveLength(1);
    const [path, init] = apiFetch.mock.calls[0] as [string, { method: string }];
    expect(path).toBe("/api/ai/active-context");
    expect(init.method).toBe("POST");
  });

  it("carries the focus object beside the top-level workflow id", () => {
    reportWorkspaceFocus(stateWith([workflowTab()], "tab-wf", "wf-1"));
    expect(lastBody()).toEqual({
      workflow_id: "wf-1",
      focus: { mode: "canvas", workflow_id: "wf-1" },
    });
  });

  it("carries the explore session's identifiers", () => {
    const tab = exploreTab();
    useAppStore.getState().applyExploreSession({
      session_id: "sess-1",
      notebook_path: PATH,
      has_kernel: false,
      needs_restart: false,
      current_cell: "c2",
      notebook_commit: null,
      bound_run: null,
      cells: [{ cell_id: "c2", cell_type: "code", source: "", enabled: true, marks: [] }],
    });
    reportWorkspaceFocus(stateWith([tab], tab.id, "wf-1"));
    expect(lastBody().focus).toEqual({
      mode: "explore",
      workflow_id: "wf-1",
      session_path: PATH,
      bound_run_id: "run-7",
      // The current cell comes from the session the runtime reported, not from
      // anything the tab remembers (FR-034).
      current_cell_id: "c2",
    });
  });

  it("does not report the same focus twice", () => {
    const state = stateWith([workflowTab()], "tab-wf", "wf-1");
    reportWorkspaceFocus(state);
    reportWorkspaceFocus(state);
    expect(focusBodies()).toHaveLength(1);
  });

  it("reports again when the person moves to a session and back", () => {
    const tab = exploreTab();
    reportWorkspaceFocus(stateWith([workflowTab(), tab], "tab-wf", "wf-1"));
    reportWorkspaceFocus(stateWith([workflowTab(), tab], tab.id, "wf-1"));
    reportWorkspaceFocus(stateWith([workflowTab(), tab], "tab-wf", "wf-1"));
    expect(focusBodies().map((body) => (body.focus as { mode: string }).mode)).toEqual([
      "canvas",
      "explore",
      "canvas",
    ]);
  });

  it("swallows a failed report rather than blocking the editor", async () => {
    apiFetch.mockRejectedValueOnce(new Error("offline"));
    expect(() => reportWorkspaceFocus(stateWith([workflowTab()], "tab-wf", "wf-1"))).not.toThrow();
    await Promise.resolve();
  });
});

describe("the focus key", () => {
  it("distinguishes two sessions and two cells", () => {
    const a = deriveWorkspaceFocus([exploreTab()], `explore:${PATH}`, "wf-1", "c1");
    const b = deriveWorkspaceFocus([exploreTab()], `explore:${PATH}`, "wf-1", "c2");
    expect(workspaceFocusKey(a)).not.toBe(workspaceFocusKey(b));
    expect(workspaceFocusKey(a)).toBe(workspaceFocusKey({ ...a }));
  });
});

describe("the pre-existing workflow sync is unchanged", () => {
  it("omits the focus key rather than sending null", async () => {
    // The backend tells "no focus key" from `"focus": null` through
    // `model_fields_set`: the first leaves the stored focus alone, the second
    // clears it. A workflow change means the first.
    const { postActiveWorkflowContext } = await import("../lib/api/ai");
    await postActiveWorkflowContext("wf-2");
    const body = lastBody();
    expect(body).toEqual({ workflow_id: "wf-2" });
    expect("focus" in body).toBe(false);
  });

  it("clears the focus when asked to, explicitly", async () => {
    const { postWorkspaceFocus } = await import("../lib/api/ai");
    await postWorkspaceFocus(null);
    expect(lastBody()).toEqual({ workflow_id: null, focus: null });
  });
});
