import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../../../store";
import { ChatMessageList } from "../ChatMessageList";

describe("ChatMessageList — in-flight Thinking… indicator (#782)", () => {
  beforeEach(() => {
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
  afterEach(() => cleanup());

  it("does not render the indicator by default", () => {
    useAppStore.getState().appendEvent("c1", { kind: "done", raw: {} });
    render(<ChatMessageList chatId="c1" />);
    expect(screen.queryByTestId("aichat-inflight-indicator")).toBeNull();
  });

  it("renders the indicator when showThinkingIndicator=true (with existing events)", () => {
    useAppStore.getState().appendEvent("c1", {
      kind: "user_message",
      raw: { content: "hi" },
    } as never);
    render(<ChatMessageList chatId="c1" showThinkingIndicator />);
    expect(screen.getByTestId("aichat-inflight-indicator")).toBeInTheDocument();
  });

  it("renders the indicator even when the event list is empty", () => {
    // Edge case: indicator should still appear if for some reason the
    // user_message event hasn't been recorded yet.
    render(<ChatMessageList chatId="c2" showThinkingIndicator />);
    expect(screen.getByTestId("aichat-inflight-indicator")).toBeInTheDocument();
    // The empty-state message should NOT show in this case.
    expect(screen.queryByTestId("chat-empty")).toBeNull();
  });

  it("hides the indicator once showThinkingIndicator=false", () => {
    useAppStore.getState().appendEvent("c3", {
      kind: "assistant_text_delta",
      raw: {},
      delta: "hello",
    } as never);
    const { rerender } = render(<ChatMessageList chatId="c3" showThinkingIndicator />);
    expect(screen.getByTestId("aichat-inflight-indicator")).toBeInTheDocument();
    rerender(<ChatMessageList chatId="c3" showThinkingIndicator={false} />);
    expect(screen.queryByTestId("aichat-inflight-indicator")).toBeNull();
  });
});

describe("ChatMessageList — textarea max-height bound (#782)", () => {
  // This is an indirect assertion. The textarea lives in AIChat, not in
  // ChatMessageList. The class-assertion test lives alongside AIChat.
  it("placeholder for organisation", () => {
    expect(true).toBe(true);
  });
});
