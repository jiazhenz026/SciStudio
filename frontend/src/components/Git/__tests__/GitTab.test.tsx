/**
 * #972 — GitTab tests.
 *
 * GitTab is a thin composition container: it owns the modal-open local
 * state and renders BranchPicker / GitStatusBadge / Commit buttons in
 * a sticky top bar above GitHistoryList. These tests assert the
 * wiring (empty-state, top-bar buttons, history list mount, button
 * → dialog open path) without re-exercising the children's internals
 * (covered by their own test files).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GitTab } from "../GitTab";
import { useAppStore } from "../../../store";
import type { GitBranch, GitStatus, ProjectResponse } from "../../../types/api";

const project: ProjectResponse = {
  id: "p1",
  name: "test",
  description: "",
  path: "/tmp/p1",
  last_opened: "2026-01-01",
  current_workflow_id: null,
  workflow_count: 0,
  workflows: [],
};

const cleanStatus: GitStatus = {
  dirty: false,
  modified: [],
  staged: [],
  untracked: [],
  conflicted: [],
};

const branches: GitBranch[] = [{ name: "main", head_sha: "a".repeat(40), is_current: true }];

function seedStore(overrides: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({
    currentProject: project,
    branches,
    currentBranch: "main",
    status: cleanStatus,
    logCache: {},
    logLoading: {},
    historyFilter: "manual",
    loadBranches: vi.fn().mockResolvedValue(undefined),
    loadStatus: vi.fn().mockResolvedValue(undefined),
    loadLog: vi.fn().mockResolvedValue(undefined),
    setHistoryFilter: vi.fn(),
    restore: vi.fn().mockResolvedValue({ status: "applied" }),
    switchBranch: vi.fn().mockResolvedValue(undefined),
    createBranch: vi.fn().mockResolvedValue(undefined),
    deleteBranch: vi.fn().mockResolvedValue(undefined),
    commit: vi.fn().mockResolvedValue("abcdef0"),
    openFileTab: vi.fn(),
    setMergeFlowSource: vi.fn(),
    mergeFlowSource: null,
    ...overrides,
  });
}

beforeEach(() => seedStore());

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GitTab — empty state", () => {
  it("renders empty-state when no project is open", () => {
    seedStore({ currentProject: null });
    render(<GitTab />);
    expect(screen.getByTestId("git-tab-empty")).toBeTruthy();
    // The active surface should NOT mount when no project — neither the
    // top bar nor the history list should be present.
    expect(screen.queryByTestId("git-tab")).toBeNull();
    expect(screen.queryByTestId("git-tab-top-bar")).toBeNull();
  });
});

describe("GitTab — composed surface", () => {
  it("renders the top bar, the three action affordances, and the history list when a project is open", () => {
    render(<GitTab />);

    expect(screen.getByTestId("git-tab")).toBeTruthy();
    expect(screen.getByTestId("git-tab-top-bar")).toBeTruthy();

    // BranchPicker, GitStatusBadge, Commit — by their stable testids.
    // ADR-039 Addendum 1 (#1353): the Stashes button is gone.
    expect(screen.getByTestId("branch-picker-trigger")).toBeTruthy();
    expect(screen.getByTestId("git-status-badge")).toBeTruthy();
    expect(screen.getByTestId("git-tab-commit-button")).toBeTruthy();
    expect(screen.queryByTestId("git-tab-stashes-button")).toBeNull();

    // GitHistoryList mounts (previously orphaned — #972 reason for this PR).
    expect(screen.getByTestId("git-history-list")).toBeTruthy();
  });

  it("clicking Commit opens the CommitDialog", () => {
    render(<GitTab />);
    // Before click — dialog not visible.
    expect(screen.queryByTestId("commit-dialog")).toBeNull();
    fireEvent.click(screen.getByTestId("git-tab-commit-button"));
    expect(screen.getByTestId("commit-dialog")).toBeTruthy();
  });
});
