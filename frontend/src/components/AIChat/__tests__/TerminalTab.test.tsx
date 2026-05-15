/**
 * ADR-035 §3.5 / §3.9 — Tests for AiBlockStatusBadge and MarkDoneButton.
 *
 * The badge variants and the Mark-done button visibility rules are the two
 * UI surfaces the user actually interacts with for the AI Block escape-hatch
 * path. We render them in isolation (with the store pre-populated) rather
 * than mounting the whole TerminalTabs container — keeps the suite snappy
 * and lets us cover all four status variants without xterm side effects.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import type { AiBlockStatus, TerminalTab } from "../../../store/types";
import { AiBlockStatusBadge, MarkDoneButton } from "../TerminalTab";

vi.mock("../../../hooks/useWebSocket", () => ({
  sendWebSocketMessage: vi.fn(),
}));

import { sendWebSocketMessage } from "../../../hooks/useWebSocket";

function seedTab(partial: Partial<TerminalTab> & { id: string }) {
  const tab: TerminalTab = {
    title: "🤖 demo",
    provider: "claude-code",
    permissionMode: "safe",
    state: "running",
    source: "ai-block",
    blockRunId: "run-x",
    blockStatus: "paused",
    ...partial,
  };
  useAppStore.setState({
    terminalTabs: [tab],
    activeTerminalTabId: tab.id,
  });
}

beforeEach(() => {
  useAppStore.setState({ terminalTabs: [], activeTerminalTabId: null });
  (sendWebSocketMessage as unknown as { mockClear: () => void }).mockClear();
});

afterEach(() => {
  cleanup();
});

describe("AiBlockStatusBadge", () => {
  it.each<[AiBlockStatus, string]>([
    ["done", "done"],
    ["error", "error"],
    ["cancelled", "cancelled"],
    ["paused", "paused"],
    ["running", "running"],
  ])("renders the %s variant", (status, expected) => {
    seedTab({ id: `t-${status}`, blockStatus: status });
    render(<AiBlockStatusBadge tabId={`t-${status}`} />);
    const el = screen.getByTestId(`ai-block-status-badge-t-${status}`);
    expect(el.getAttribute("data-status")).toBe(expected);
  });

  it("renders nothing when source is not ai-block", () => {
    seedTab({ id: "user-tab", source: "user" });
    const { container } = render(<AiBlockStatusBadge tabId="user-tab" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when tab does not exist", () => {
    const { container } = render(<AiBlockStatusBadge tabId="missing" />);
    expect(container.firstChild).toBeNull();
  });
});

describe("MarkDoneButton", () => {
  it("renders the button when source=ai-block and status=paused", () => {
    seedTab({ id: "btn-1", blockStatus: "paused" });
    render(<MarkDoneButton tabId="btn-1" />);
    expect(screen.getByTestId("mark-done-btn-btn-1")).toBeInTheDocument();
  });

  it.each<AiBlockStatus>(["done", "error", "cancelled", "running"])(
    "is hidden when blockStatus=%s",
    (status) => {
      seedTab({ id: `btn-${status}`, blockStatus: status });
      const { container } = render(
        <MarkDoneButton tabId={`btn-${status}`} />,
      );
      expect(container.firstChild).toBeNull();
    },
  );

  it("is hidden when source is not ai-block", () => {
    seedTab({ id: "user-btn", source: "user" });
    const { container } = render(<MarkDoneButton tabId="user-btn" />);
    expect(container.firstChild).toBeNull();
  });

  it("click sends block_user_marked_done WS message addressed to the run", () => {
    seedTab({
      id: "btn-click",
      blockStatus: "paused",
      blockRunId: "run-click",
    });
    render(<MarkDoneButton tabId="btn-click" />);
    fireEvent.click(screen.getByTestId("mark-done-btn-btn-click"));
    expect(sendWebSocketMessage).toHaveBeenCalledWith({
      type: "block_user_marked_done",
      block_run_id: "run-click",
      tab_id: "btn-click",
    });
  });

  it("click is a no-op when blockRunId is missing", () => {
    seedTab({
      id: "btn-no-run",
      blockStatus: "paused",
      blockRunId: undefined,
    });
    render(<MarkDoneButton tabId="btn-no-run" />);
    fireEvent.click(screen.getByTestId("mark-done-btn-btn-no-run"));
    expect(sendWebSocketMessage).not.toHaveBeenCalled();
  });
});
