import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { AIChat } from "../AIChat";

// Mock the WS hook so we can control sendMessage's return value and
// avoid opening real sockets in unit tests.
const sendMessageMock = vi.fn(() => true);
vi.mock("../../../hooks/useAgentWebSocket", () => ({
  useAgentWebSocket: () => ({
    state: "open",
    sendMessage: sendMessageMock,
    cancel: vi.fn(),
    sendPermissionDecision: vi.fn(),
  }),
}));

describe("AIChat — in-flight Thinking… indicator (#782 Bug 2)", () => {
  beforeEach(() => {
    sendMessageMock.mockClear();
    sendMessageMock.mockReturnValue(true);
    useAppStore.setState({
      activeChatId: "chat-1",
      currentProject: { path: "/tmp/proj", name: "p" } as never,
      sessions: [{ id: "chat-1", title: "c", createdAt: 0, ended: false } as never],
      eventsByChat: {},
      pendingPermissions: {},
      permissionMode: "strict",
      providerName: "claude-code",
      alwaysAllowedTools: {},
    });
  });
  afterEach(() => cleanup());

  it("textarea has max-height and overflow-y-auto to bound growth (#782 Bug 3)", () => {
    render(<AIChat />);
    const ta = screen.getByTestId("aichat-input") as HTMLTextAreaElement;
    expect(ta.className).toMatch(/max-h-\[200px\]/);
    expect(ta.className).toMatch(/overflow-y-auto/);
    expect(ta.className).toMatch(/resize-none/);
  });

  it("shows the in-flight indicator after user send, hides it on first agent event", async () => {
    const { getByTestId, queryByTestId } = render(<AIChat />);

    // Initially: no indicator (no user_message sent yet).
    expect(queryByTestId("aichat-inflight-indicator")).toBeNull();

    // Type and send.
    const ta = getByTestId("aichat-input") as HTMLTextAreaElement;
    act(() => {
      ta.focus();
      // jsdom-friendly value change: dispatch input event via React.
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      setter?.call(ta, "hello agent");
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() => {
      getByTestId("aichat-send").click();
    });

    // Indicator visible now.
    expect(getByTestId("aichat-inflight-indicator")).toBeInTheDocument();

    // Simulate a real assistant event arriving.
    act(() => {
      useAppStore.getState().appendEvent("chat-1", {
        kind: "assistant_text_delta",
        raw: {},
        delta: "hi back",
      } as never);
    });

    // Indicator gone.
    expect(queryByTestId("aichat-inflight-indicator")).toBeNull();
  });
});
