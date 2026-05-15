/**
 * D39-2.3b — BranchPicker tests.
 *
 * We focus on the trigger button + the loadBranches dispatch path. The
 * actual menu items render inside a Radix portal; full menu-open testing
 * is exercised in the Chrome smoke (Radix dropdowns are notoriously fiddly
 * under jsdom because of pointer-events / animation handling).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BranchPicker } from "../BranchPicker";
import { useAppStore } from "../../../store";
import type { GitBranch } from "../../../types/api";

const twoBranches: GitBranch[] = [
  { name: "main", head_sha: "a".repeat(40), is_current: true },
  { name: "experiment-1", head_sha: "b".repeat(40), is_current: false },
];

function seedStore(overrides: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({
    branches: twoBranches,
    currentBranch: "main",
    loadBranches: vi.fn().mockResolvedValue(undefined),
    switchBranch: vi.fn().mockResolvedValue(undefined),
    createBranch: vi.fn().mockResolvedValue(undefined),
    deleteBranch: vi.fn().mockResolvedValue(undefined),
    currentProject: {
      id: "p1",
      name: "test",
      description: "",
      path: "/tmp/p1",
      last_opened: "2026-01-01",
      current_workflow_id: null,
      workflow_count: 0,
      workflows: [],
    },
    ...overrides,
  });
}

beforeEach(() => seedStore());

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BranchPicker", () => {
  it("trigger label shows currentBranch name", () => {
    render(<BranchPicker />);
    const trigger = screen.getByTestId("branch-picker-trigger");
    expect(trigger.textContent).toContain("main");
  });

  it("trigger label falls back to 'no branch' when currentBranch is null and branches loaded", () => {
    seedStore({ currentBranch: null, branches: [] });
    render(<BranchPicker />);
    expect(screen.getByTestId("branch-picker-trigger").textContent).toContain("no branch");
  });

  it("trigger label is 'loading…' while branches === null", () => {
    seedStore({ currentBranch: null, branches: null });
    render(<BranchPicker />);
    expect(screen.getByTestId("branch-picker-trigger").textContent).toContain("loading");
  });

  it("aria-label on trigger reflects current branch", () => {
    seedStore({ currentBranch: "experiment-1" });
    render(<BranchPicker />);
    const trigger = screen.getByTestId("branch-picker-trigger");
    expect(trigger.getAttribute("aria-label")).toBe("Current branch: experiment-1");
  });

  it("dispatches loadBranches on mount when branches is null", async () => {
    const loadBranches = vi.fn().mockResolvedValue(undefined);
    seedStore({ branches: null, loadBranches });
    render(<BranchPicker />);
    await waitFor(() => expect(loadBranches).toHaveBeenCalledTimes(1));
  });

  it("does not call loadBranches when branches is already populated", () => {
    const loadBranches = vi.fn();
    seedStore({ loadBranches });
    render(<BranchPicker />);
    expect(loadBranches).not.toHaveBeenCalled();
  });

  /*
   * Radix DropdownMenu uses pointer-events + portal rendering that does
   * not fully exercise under jsdom (the menu Content does not mount on a
   * plain `click`). The smoke-test in Chrome MCP covers the full
   * open-menu / click-item interaction. Here we only assert the static
   * trigger contract; menu-open + item-click behavior is verified live.
   */
});
