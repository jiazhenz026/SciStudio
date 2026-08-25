/**
 * ADR-053 FR-061a / #2083 — the replay-tab adoption effect.
 *
 * `session.replay = {surface, tab_id}` was typed on the session response and
 * consumed by nothing; this hook is the consumer. The tests cover the three
 * rules the module comment states: adopt only on a change observed while the
 * page is alive, tear down when the session lets the replay go, and never
 * re-adopt an unchanged id.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import type { TutorialSessionResponse } from "../../lib/api/learningCenter";
import { TUTORIAL_REPLAY_TAB_TITLE, useTutorialReplayTab } from "../useTutorialReplayTab";

function session(replayTabId: string | null): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "what-ai-can-do",
    title: "What AI can do",
    project_id: "proj-1",
    project_path: "/tmp/what-ai-can-do",
    step: null,
    satisfied_step_ids: [],
    status: "active",
    error: null,
    replay: replayTabId === null ? null : { surface: "ai_chat_terminal", tab_id: replayTabId },
  };
}

function Host() {
  useTutorialReplayTab();
  return null;
}

describe("useTutorialReplayTab (#2083)", () => {
  beforeEach(() => {
    resetAppStore();
    useAppStore.setState({ terminalTabs: [], activeTerminalTabId: null });
  });

  afterEach(() => {
    // Unmount between tests: a Host left mounted from an earlier test would
    // keep watching the store and adopt what the next test sets up.
    cleanup();
    resetAppStore();
  });

  it("adopts a replay that opens while the page is watching, into the AI bottom tab", () => {
    render(<Host />);

    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-1") });
    });

    const tabs = useAppStore.getState().terminalTabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0]).toMatchObject({
      id: "replay-1",
      title: TUTORIAL_REPLAY_TAB_TITLE,
      state: "running",
      source: "tutorial-replay",
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe("replay-1");
    // The reply the reader just asked for appears where they can see it.
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
    expect(useAppStore.getState().bottomPanelCollapsed).toBe(false);
  });

  it("never adopts the replay it woke up to: that session died with the last page", () => {
    // The store already carries a replay before the hook's first look — the
    // reload case. Its scripted byte source was torn down when the previous
    // page's WebSocket closed, and joining the stale id would spawn a real
    // shell (the PTY route's unknown-id branch spawns).
    useAppStore.setState({ learningCenterSession: session("stale-replay") });

    render(<Host />);

    expect(useAppStore.getState().terminalTabs).toHaveLength(0);
  });

  it("does not thrash on an unchanged id, and appended segments change nothing", () => {
    render(<Host />);
    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-1") });
    });
    const adopted = useAppStore.getState().terminalTabs[0];

    // continue_tab replays (#2089) re-deliver the same tab id on every
    // trigger response; the adoption must be a no-op.
    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-1") });
    });

    expect(useAppStore.getState().terminalTabs).toHaveLength(1);
    expect(useAppStore.getState().terminalTabs[0]).toBe(adopted);
  });

  it("closes the adopted tab when the session lets the replay go", () => {
    render(<Host />);
    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-1") });
    });
    expect(useAppStore.getState().terminalTabs).toHaveLength(1);

    // Leaving, finishing, or erroring the session all clear `replay`;
    // finishing clears the whole session. Either shape must tear down.
    act(() => {
      useAppStore.setState({ learningCenterSession: null });
    });

    expect(useAppStore.getState().terminalTabs).toHaveLength(0);
  });

  it("swaps tabs when a later session opens a new replay", () => {
    render(<Host />);
    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-1") });
    });
    act(() => {
      useAppStore.setState({ learningCenterSession: session("replay-2") });
    });

    const tabs = useAppStore.getState().terminalTabs;
    expect(tabs.map((tab) => tab.id)).toEqual(["replay-2"]);
  });
});
