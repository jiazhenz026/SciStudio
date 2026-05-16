/**
 * D39-2.3b — GitHistoryList tests.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GitHistoryList } from "../GitHistoryList";
import { useAppStore } from "../../../store";
import type { GitCommit } from "../../../types/api";

function mkCommit(subject: string, sha: string): GitCommit {
  return {
    sha,
    short_sha: sha.slice(0, 7),
    parents: [],
    author_name: "Test User",
    author_email: "t@example.com",
    author_date: "2026-05-15T00:00:00Z",
    subject,
    body: "",
    branches: [],
  };
}

const userCommit = mkCommit("feat: user commit", "aaaaaaa1");
const autoCommit = mkCommit("auto: pre-run @ 2026-05-15", "bbbbbbb2");
const agentCommit = mkCommit("agent: agent change", "ccccccc3");
const allCommits = [userCommit, autoCommit, agentCommit];

function seed(branch: string, commits: GitCommit[] | undefined, loading = false) {
  const key = branch && branch.length > 0 ? branch : "<all>";
  useAppStore.setState({
    logCache: commits === undefined ? {} : { [key]: commits },
    logLoading: { [key]: loading },
    historyFilter: "manual",
    loadLog: vi.fn().mockResolvedValue(undefined),
    setHistoryFilter: (filter) =>
      useAppStore.setState({ historyFilter: filter }),
    restore: vi.fn().mockResolvedValue(undefined),
  });
}

beforeEach(() => seed("main", allCommits));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/**
 * Hotfix #1000: GitHistoryList now defaults to Graph view. These tests
 * all assert on the LIST view's row testids; flip to list mode after
 * render so the existing test contracts keep working.
 */
function flipToListView(): void {
  const listBtn = screen.queryByTestId("git-history-view-list");
  if (listBtn) fireEvent.click(listBtn);
}

describe("GitHistoryList", () => {
  it("renders loading state when logLoading[branch] === true", () => {
    seed("main", undefined, true);
    render(<GitHistoryList branch="main" />);
    flipToListView();
    expect(screen.getByTestId("git-history-loading")).toBeTruthy();
  });

  it("renders empty state when logCache[branch] === []", () => {
    seed("main", []);
    render(<GitHistoryList branch="main" />);
    flipToListView();
    expect(screen.getByTestId("git-history-empty")).toBeTruthy();
  });

  it("filter dropdown default 'manual' hides auto: and agent: rows", () => {
    render(<GitHistoryList branch="main" />);
    flipToListView();
    const filter = screen.getByTestId("git-history-filter") as HTMLSelectElement;
    expect(filter.value).toBe("manual");
    expect(screen.queryByTestId(`git-history-row-${autoCommit.short_sha}`)).toBeNull();
    expect(screen.queryByTestId(`git-history-row-${agentCommit.short_sha}`)).toBeNull();
    expect(screen.getByTestId(`git-history-row-${userCommit.short_sha}`)).toBeTruthy();
  });

  it("changing filter to 'all' reveals auto + agent rows", () => {
    render(<GitHistoryList branch="main" />);
    flipToListView();
    fireEvent.change(screen.getByTestId("git-history-filter"), {
      target: { value: "all" },
    });
    expect(screen.getByTestId(`git-history-row-${userCommit.short_sha}`)).toBeTruthy();
    expect(screen.getByTestId(`git-history-row-${autoCommit.short_sha}`)).toBeTruthy();
    expect(screen.getByTestId(`git-history-row-${agentCommit.short_sha}`)).toBeTruthy();
  });

  it("filter 'agent' shows only agent rows", () => {
    render(<GitHistoryList branch="main" />);
    flipToListView();
    fireEvent.change(screen.getByTestId("git-history-filter"), {
      target: { value: "agent" },
    });
    expect(screen.getByTestId(`git-history-row-${agentCommit.short_sha}`)).toBeTruthy();
    expect(screen.queryByTestId(`git-history-row-${userCommit.short_sha}`)).toBeNull();
  });

  it("shows empty-after-filter message when no commits match filter", () => {
    seed("main", [autoCommit]); // only auto: commits
    render(<GitHistoryList branch="main" />);
    flipToListView();
    expect(screen.getByTestId("git-history-empty-after-filter")).toBeTruthy();
  });

  it("clicking a row dispatches onCommitClick", () => {
    const onCommitClick = vi.fn();
    render(<GitHistoryList branch="main" onCommitClick={onCommitClick} />);
    flipToListView();
    fireEvent.click(screen.getByTestId(`git-history-row-${userCommit.short_sha}`));
    expect(onCommitClick).toHaveBeenCalledWith(expect.objectContaining({ sha: userCommit.sha }));
  });

  it("clicking restore dispatches onRestoreClick and stops propagation", () => {
    const onCommitClick = vi.fn();
    const onRestoreClick = vi.fn();
    render(
      <GitHistoryList
        branch="main"
        onCommitClick={onCommitClick}
        onRestoreClick={onRestoreClick}
      />,
    );
    flipToListView();
    fireEvent.click(screen.getByTestId(`git-history-row-restore-${userCommit.short_sha}`));
    expect(onRestoreClick).toHaveBeenCalledWith(
      expect.objectContaining({ sha: userCommit.sha }),
    );
    expect(onCommitClick).not.toHaveBeenCalled();
  });

  it("dispatches loadLog on mount when logCache[branch] is missing", async () => {
    const loadLog = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ logCache: {}, logLoading: {}, loadLog });
    render(<GitHistoryList branch="feature" />);
    await waitFor(() => expect(loadLog).toHaveBeenCalledWith("feature"));
  });

  it("Refresh button re-dispatches loadLog", () => {
    const loadLog = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ loadLog });
    render(<GitHistoryList branch="main" />);
    flipToListView();
    fireEvent.click(screen.getByTestId("git-history-refresh"));
    expect(loadLog).toHaveBeenCalledWith("main");
  });
});
