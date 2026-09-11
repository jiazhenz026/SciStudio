import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useEffect } from "react";
import { BottomPanel } from "./BottomPanel";
import { setPresentation } from "../lib/presentation";

const lifecycle = vi.hoisted(() => ({ mount: vi.fn(), unmount: vi.fn() }));
vi.mock("./AIChat/TerminalTabs", () => ({
  TerminalTabs: ({ surface }: { surface: string }) => {
    useEffect(() => {
      lifecycle.mount(surface);
      return () => lifecycle.unmount(surface);
    }, [surface]);
    return <div data-testid={`terminal-${surface}`} />;
  },
}));
vi.mock("./BottomPanel.parts/ConfigPanel", () => ({
  ConfigPanel: () => <div>Node configuration</div>,
}));
vi.mock("./BottomPanel.parts/PlotsTab", () => ({ PlotsTab: () => null }));
vi.mock("./Git/GitTab", () => ({ GitTab: () => null }));
vi.mock("./Lineage/LineageTab", () => ({ LineageTab: () => null }));

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.clearAllMocks();
});

const props = {
  activeTab: "ai" as const,
  selectedNode: null,
  logEntries: [],
  onTabChange: vi.fn(),
  onUpdateConfig: vi.fn(),
};

it("direct AI entry omits chat initialization and renders Config for a stale AI selection", () => {
  setPresentation("ai");
  render(<BottomPanel {...props} />);
  expect(screen.queryByRole("button", { name: "AI Chat" })).not.toBeInTheDocument();
  expect(screen.getByText("Node configuration")).toBeVisible();
  expect(lifecycle.mount).not.toHaveBeenCalledWith("chat");
  expect(screen.getByRole("button", { name: "Terminal" })).toBeVisible();
});

it("changing layout preserves already mounted chat and terminal sessions", () => {
  render(<BottomPanel {...props} />);
  const chat = screen.getByTestId("terminal-chat");
  const terminal = screen.getByTestId("terminal-terminal");
  act(() => setPresentation("ai"));
  expect(chat).not.toBeVisible();
  expect(lifecycle.unmount).not.toHaveBeenCalled();
  act(() => setPresentation("workbench"));
  expect(screen.getByTestId("terminal-chat")).toBe(chat);
  expect(screen.getByTestId("terminal-terminal")).toBe(terminal);
  expect(screen.getByRole("button", { name: "AI Chat" })).toBeVisible();
});
