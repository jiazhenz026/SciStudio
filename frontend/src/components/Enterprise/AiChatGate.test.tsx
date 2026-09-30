/**
 * ADR-055 Spec 4 FR-006 — `ai_chat_disabled` hides the AI Chat surface (#2322;
 * story 6). The Terminal tab is never gated, and without the capability the
 * bottom panel is unchanged. The backend half of the gate is covered by
 * `tests/api/test_ai_pty_capability.py`.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetCapabilitiesCacheForTests } from "../../lib/capabilities";
import { BottomPanel } from "../BottomPanel";

function declare(value: unknown): void {
  if (value === undefined) {
    delete window.__SCISTUDIO_CAPABILITIES__;
  } else {
    window.__SCISTUDIO_CAPABILITIES__ = value;
  }
  resetCapabilitiesCacheForTests();
}

function renderPanel(onTabChange = vi.fn()) {
  return render(
    <BottomPanel
      activeTab="ai"
      logEntries={[]}
      onTabChange={onTabChange}
      onUpdateConfig={() => {}}
      selectedNode={null}
    />,
  );
}

afterEach(() => {
  cleanup();
  declare(undefined);
});

describe("the AI Chat surface", () => {
  it("is present without the capability", () => {
    declare(undefined);
    renderPanel();
    expect(screen.getByRole("button", { name: "AI Chat" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Terminal" })).toBeInTheDocument();
  });

  it("is present when the edition declares other capabilities", () => {
    declare({ version: 1, identity: { user: "alice" } });
    renderPanel();
    expect(screen.getByRole("button", { name: "AI Chat" })).toBeInTheDocument();
  });

  it("is hidden when ai_chat_disabled is set, and the Terminal stays", () => {
    declare({ version: 1, aiChatDisabled: true });
    renderPanel();
    expect(screen.queryByRole("button", { name: "AI Chat", hidden: true })).toBeNull();
    expect(screen.getByRole("button", { name: "Terminal" })).toBeInTheDocument();
    // A request for the AI tab lands on Config, as it does in AI presentation.
    expect(screen.getByRole("button", { name: "Config" })).toHaveClass("bg-ink");
  });
});
