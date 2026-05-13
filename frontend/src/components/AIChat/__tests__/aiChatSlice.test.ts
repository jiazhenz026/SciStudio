import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../../../store";

describe("aiChatSlice", () => {
  beforeEach(() => {
    // Reset slice state between tests.
    useAppStore.setState({
      activeChatId: null,
      sessions: [],
      eventsByChat: {},
      pendingPermissions: {},
      permissionMode: "strict",
      providerName: "claude-code",
      alwaysAllowedTools: {},
    });
  });

  it("appendEvent registers a session on first event", () => {
    useAppStore.getState().appendEvent("chat-1", {
      kind: "done",
      raw: {},
    });
    const state = useAppStore.getState();
    expect(state.eventsByChat["chat-1"]).toHaveLength(1);
    expect(state.sessions.map((s) => s.id)).toContain("chat-1");
  });

  it("createSession is idempotent", () => {
    useAppStore.getState().createSession("chat-x", "X");
    useAppStore.getState().createSession("chat-x", "Y");
    expect(useAppStore.getState().sessions.filter((s) => s.id === "chat-x")).toHaveLength(1);
  });

  it("renameSession updates title", () => {
    useAppStore.getState().createSession("chat-r", "old");
    useAppStore.getState().renameSession("chat-r", "new");
    expect(useAppStore.getState().sessions.find((s) => s.id === "chat-r")?.title).toBe("new");
  });

  it("removeSession clears events and pending permission", () => {
    useAppStore.getState().appendEvent("chat-r", { kind: "done", raw: {} });
    useAppStore.getState().setPendingPermission("chat-r", {
      requestId: "r",
      toolName: "Edit",
      toolInput: {},
    });
    useAppStore.getState().setActiveChatId("chat-r");
    useAppStore.getState().removeSession("chat-r");
    const state = useAppStore.getState();
    expect(state.sessions.find((s) => s.id === "chat-r")).toBeUndefined();
    expect(state.eventsByChat["chat-r"]).toBeUndefined();
    expect(state.pendingPermissions["chat-r"]).toBeUndefined();
    expect(state.activeChatId).toBeNull();
  });

  it("markSessionEnded flips the ended flag", () => {
    useAppStore.getState().createSession("chat-e");
    useAppStore.getState().markSessionEnded("chat-e");
    expect(useAppStore.getState().sessions.find((s) => s.id === "chat-e")?.ended).toBe(true);
  });

  it("markAlwaysAllowed records the tool name", () => {
    useAppStore.getState().markAlwaysAllowed("Read");
    expect(useAppStore.getState().alwaysAllowedTools["Read"]).toBe(true);
  });
});
