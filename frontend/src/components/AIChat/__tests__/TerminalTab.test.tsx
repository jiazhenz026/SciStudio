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
import type { AiBlockStatus, TerminalTab as TerminalTabState } from "../../../store/types";
import type { WorkflowEventMessage } from "../../../types/api";
import { AiBlockStatusBadge, MarkDoneButton, TerminalTab } from "../TerminalTab";

vi.mock("../../../hooks/useWebSocket", () => ({
  sendWebSocketMessage: vi.fn(),
}));

import { sendWebSocketMessage } from "../../../hooks/useWebSocket";

function seedTab(partial: Partial<TerminalTabState> & { id: string }) {
  const tab: TerminalTabState = {
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
      const { container } = render(<MarkDoneButton tabId={`btn-${status}`} />);
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

describe("TerminalTab closed state", () => {
  it("shows the preserved PTY error instead of the reload-only message", () => {
    seedTab({
      id: "closed-error",
      source: "user",
      state: "closed",
      exitCode: -2,
      errorMessage: "Failed to spawn PTY: codex not found",
    });
    render(<TerminalTab tabId="closed-error" />);
    expect(screen.getByTestId("terminal-tab-closed-closed-error").textContent).toContain(
      "Terminal failed: Failed to spawn PTY: codex not found",
    );
    expect(screen.getByTestId("terminal-tab-closed-closed-error").textContent).not.toContain(
      "page reload",
    );
  });
});

/**
 * ADR-034 FR-020c / FR-022 — the engine-initiated tab must record the provider
 * the engine actually spawned, across all four links of the path:
 *
 *   1. the `block_pty_opened` payload type
 *   2. the WS dispatch in `hooks/useWebSocket.parts/handleBlockPty.ts`
 *   3. `handleBlockPtyOpened` in `components/AIChat/blockPtyHandlers.ts`
 *   4. `addAiBlockTerminalTab` in `store/terminalTabsSlice.ts`
 *
 * These tests enter at link 2 (the real WS frame) so links 2-4 run for real,
 * and additionally probe links 3 and 4 in isolation. The spec's point is that
 * fixing only some links leaves the others able to substitute the old
 * hardcoded `"claude-code"`, so every test here uses a NON-default provider
 * and the negative tests assert an error rather than a silent fallback.
 */
describe("ADR-034 — provider threading on the engine-initiated tab path", () => {
  const NOW = "2026-08-06T00:00:00Z";

  function wsFrame(over: Record<string, unknown>): WorkflowEventMessage {
    return {
      type: "block_pty_opened",
      block_id: "blk",
      workflow_id: "wf",
      data: {},
      timestamp: NOW,
      ...over,
    } as WorkflowEventMessage;
  }

  it("records a kimi-code provider end to end, top-level on the frame", async () => {
    const { handleBlockPtyOpened: wsHandleOpened } =
      await import("../../../hooks/useWebSocket.parts/handleBlockPty");
    const appendLog = vi.fn();
    wsHandleOpened(
      wsFrame({
        tab_id: "e2e-kimi",
        block_run_id: "run-kimi",
        title: "extract",
        provider: "kimi-code",
        permission_mode: "bypass",
      }),
      { appendLog },
    );
    const tab = useAppStore.getState().terminalTabs.find((t) => t.id === "e2e-kimi");
    expect(tab).toBeDefined();
    expect(tab?.provider).toBe("kimi-code");
    expect(tab?.source).toBe("ai-block");
    expect(tab?.permissionMode).toBe("dangerous");
  });

  it("records a qoder provider end to end when the frame nests it under data", async () => {
    const { handleBlockPtyOpened: wsHandleOpened } =
      await import("../../../hooks/useWebSocket.parts/handleBlockPty");
    const appendLog = vi.fn();
    wsHandleOpened(
      wsFrame({
        data: {
          tab_id: "e2e-qoder",
          block_run_id: "run-qoder",
          block_name: "fit",
          provider: "qoder",
        },
      }),
      { appendLog },
    );
    const tab = useAppStore.getState().terminalTabs.find((t) => t.id === "e2e-qoder");
    expect(tab?.provider).toBe("qoder");
  });

  it("forwards a provider key the frontend has never heard of, unchanged", async () => {
    // FR-020a: agent keys are opaque strings. A provider added to the backend
    // registry alone must reach the tab without any frontend edit.
    const { handleBlockPtyOpened: wsHandleOpened } =
      await import("../../../hooks/useWebSocket.parts/handleBlockPty");
    wsHandleOpened(
      wsFrame({
        tab_id: "e2e-future",
        block_run_id: "run-future",
        title: "x",
        provider: "some-future-agent",
      }),
      { appendLog: vi.fn() },
    );
    expect(useAppStore.getState().terminalTabs.find((t) => t.id === "e2e-future")?.provider).toBe(
      "some-future-agent",
    );
  });

  it("link 2 (WS dispatch) errors on a frame with no provider instead of defaulting", async () => {
    const { handleBlockPtyOpened: wsHandleOpened } =
      await import("../../../hooks/useWebSocket.parts/handleBlockPty");
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const appendLog = vi.fn();
    wsHandleOpened(wsFrame({ tab_id: "no-prov-ws", block_run_id: "run-np", title: "x" }), {
      appendLog,
    });
    expect(errSpy).toHaveBeenCalled();
    expect(appendLog).toHaveBeenCalledWith(
      expect.objectContaining({ level: "error", message: expect.stringContaining("no provider") }),
    );
    // The bug this replaces: a tab silently recorded as claude-code.
    expect(useAppStore.getState().terminalTabs.find((t) => t.id === "no-prov-ws")).toBeUndefined();
    errSpy.mockRestore();
  });

  it("link 3 (blockPtyHandlers) errors on a payload with no provider instead of defaulting", async () => {
    const { handleBlockPtyOpened } = await import("../blockPtyHandlers");
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    handleBlockPtyOpened({
      tab_id: "no-prov-h",
      block_run_id: "run-np",
      title: "x",
      // Simulates an upstream link that dropped the field. Cast because the
      // contract type makes it required — that is link 3's first line of
      // defence; this asserts the runtime one behind it.
    } as unknown as Parameters<typeof handleBlockPtyOpened>[0]);
    expect(errSpy).toHaveBeenCalled();
    expect(useAppStore.getState().terminalTabs.find((t) => t.id === "no-prov-h")).toBeUndefined();
    errSpy.mockRestore();
  });

  it("link 4 (store) records exactly the provider it was handed, with no fallback", () => {
    useAppStore.getState().addAiBlockTerminalTab({
      tabId: "slice-direct",
      title: "🤖 x",
      blockRunId: "run-slice",
      permissionMode: "safe",
      provider: "qoder-cn",
    });
    const tab = useAppStore.getState().terminalTabs.find((t) => t.id === "slice-direct");
    expect(tab?.provider).toBe("qoder-cn");
    // Guard against the old hardcoded value creeping back in.
    expect(tab?.provider).not.toBe("claude-code");
  });

  it("link 4 keeps the reported provider when the engine resends the open event", async () => {
    const { handleBlockPtyOpened: wsHandleOpened } =
      await import("../../../hooks/useWebSocket.parts/handleBlockPty");
    const frame = wsFrame({
      tab_id: "idem-kimi",
      block_run_id: "run-idem",
      title: "x",
      provider: "kimi-code",
    });
    wsHandleOpened(frame, { appendLog: vi.fn() });
    wsHandleOpened(frame, { appendLog: vi.fn() });
    const tabs = useAppStore.getState().terminalTabs.filter((t) => t.id === "idem-kimi");
    expect(tabs.length).toBe(1);
    expect(tabs[0].provider).toBe("kimi-code");
  });
});
