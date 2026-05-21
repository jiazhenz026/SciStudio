/**
 * D39-2.3b — gitSlice tests.
 *
 * Pure-helper exports (classifyPrefix, selectVisibleCommits) + mutation
 * actions (loadBranches / loadLog / loadStatus / commit / ...). Mutation
 * actions now go through `api.*`, which is mocked here so no real HTTP is
 * issued. We exercise both success and failure paths.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { classifyPrefix, createGitSlice, selectVisibleCommits } from "../gitSlice";
import type { GitCommit } from "../../types/api";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    api: {
      gitBranches: vi.fn().mockResolvedValue([
        { name: "main", head_sha: "a".repeat(40), is_current: true },
      ]),
      gitLog: vi.fn().mockResolvedValue([]),
      gitStatus: vi.fn().mockResolvedValue({
        dirty: false,
        modified: [],
        staged: [],
        untracked: [],
        conflicted: [],
      }),
      gitCommit: vi.fn().mockResolvedValue({ commit_sha: "deadbee" }),
      gitBranchSwitch: vi.fn().mockResolvedValue({ status: "ok", current_branch: "main" }),
      gitBranchCreate: vi.fn().mockResolvedValue({ status: "ok", name: "x" }),
      gitBranchDelete: vi.fn().mockResolvedValue({ status: "ok" }),
      gitRestore: vi.fn().mockResolvedValue({ status: "ok" } as const),
    },
  };
});

function mk(subject: string, sha = "deadbeef"): GitCommit {
  return {
    sha,
    short_sha: sha.slice(0, 7),
    parents: [],
    author_name: "Test",
    author_email: "t@example.com",
    author_date: "2026-05-15T00:00:00Z",
    subject,
    body: "",
    branches: [],
  };
}

describe("gitSlice — pure helpers (ADR §3.4 / §3.5c)", () => {
  describe("classifyPrefix", () => {
    it("returns 'auto' for messages starting with 'auto:'", () => {
      expect(classifyPrefix("auto: pre-run @ 2026-05-15")).toBe("auto");
    });

    it("returns 'agent' for messages starting with 'agent:'", () => {
      expect(classifyPrefix("agent: bumped cellpose model")).toBe("agent");
    });

    it("returns 'user' for unprefixed messages", () => {
      expect(classifyPrefix("feat: add segmentation block")).toBe("user");
    });

    it("returns 'user' when prefix is preceded by whitespace (strict match)", () => {
      // Whitespace before the prefix MUST NOT classify as auto/agent.
      expect(classifyPrefix("  auto: indented")).toBe("user");
    });

    it("only looks at the first line", () => {
      expect(classifyPrefix("feat: x\nauto: not the prefix here")).toBe("user");
    });

    it("handles empty string defensively", () => {
      expect(classifyPrefix("")).toBe("user");
    });
  });

  describe("selectVisibleCommits", () => {
    const commits = [
      mk("feat: user commit", "aaa"),
      mk("auto: pre-run", "bbb"),
      mk("agent: agent commit", "ccc"),
    ];

    it("'manual' filter hides auto + agent commits", () => {
      const visible = selectVisibleCommits(commits, "manual");
      expect(visible.map((c) => c.short_sha)).toEqual(["aaa"]);
    });

    it("'all' filter shows every commit", () => {
      expect(selectVisibleCommits(commits, "all")).toHaveLength(3);
    });

    it("'auto' filter shows only auto: commits", () => {
      const visible = selectVisibleCommits(commits, "auto");
      expect(visible.map((c) => c.short_sha)).toEqual(["bbb"]);
    });

    it("'agent' filter shows only agent: commits", () => {
      const visible = selectVisibleCommits(commits, "agent");
      expect(visible.map((c) => c.short_sha)).toEqual(["ccc"]);
    });

    it("returns a new array (does not mutate)", () => {
      const out = selectVisibleCommits(commits, "all");
      expect(out).not.toBe(commits);
    });
  });
});

describe("gitSlice — default state shape (skeleton)", () => {
  // The factory takes (set, get, api). We pass minimal stubs because we
  // only assert defaults and synchronous setters here.
  function makeSlice() {
    let state: any = {};
    const set = (partial: any) => {
      state = typeof partial === "function" ? { ...state, ...partial(state) } : { ...state, ...partial };
    };
    const get = () => state;
    const api = {} as any;
    const slice = createGitSlice(set, get, api);
    state = { ...state, ...slice };
    return { state, set, get, slice };
  }

  it("defaults branches to null", () => {
    expect(makeSlice().slice.branches).toBeNull();
  });

  it("defaults historyFilter to 'manual'", () => {
    expect(makeSlice().slice.historyFilter).toBe("manual");
  });

  it("defaults logCache and logLoading to empty objects", () => {
    const { slice } = makeSlice();
    expect(slice.logCache).toEqual({});
    expect(slice.logLoading).toEqual({});
  });

  it("setHistoryFilter is callable (synchronous)", () => {
    const { slice } = makeSlice();
    expect(() => slice.setHistoryFilter("all")).not.toThrow();
  });

  it("setMergeInProgress is callable (synchronous)", () => {
    const { slice } = makeSlice();
    expect(() =>
      slice.setMergeInProgress({ source_branch: "x", conflicted_files: [] }),
    ).not.toThrow();
  });

  it("defaults mergeFlowSource to null (#972 — Codex P1 on PR #974)", () => {
    expect(makeSlice().slice.mergeFlowSource).toBeNull();
  });

  it("defaults mergeFlowProjectId to null (#975 — Codex P1 on PR #980)", () => {
    expect(makeSlice().slice.mergeFlowProjectId).toBeNull();
  });

  it("setMergeFlowSource updates the slice and round-trips to null", () => {
    const { slice, get } = makeSlice();
    slice.setMergeFlowSource("feature-x");
    expect(get().mergeFlowSource).toBe("feature-x");
    slice.setMergeFlowSource(null);
    expect(get().mergeFlowSource).toBeNull();
  });

  it("setMergeFlowSource stamps mergeFlowProjectId from second arg (#975)", () => {
    const { slice, get } = makeSlice();
    slice.setMergeFlowSource("feature-x", "project-A");
    expect(get().mergeFlowSource).toBe("feature-x");
    expect(get().mergeFlowProjectId).toBe("project-A");
  });

  it("setMergeFlowSource(null) clears both mergeFlowSource and mergeFlowProjectId (#975)", () => {
    const { slice, get } = makeSlice();
    slice.setMergeFlowSource("feature-x", "project-A");
    slice.setMergeFlowSource(null);
    expect(get().mergeFlowSource).toBeNull();
    expect(get().mergeFlowProjectId).toBeNull();
  });

  it("setMergeFlowSource(source) without projectId stamps null projectId (#975)", () => {
    const { slice, get } = makeSlice();
    slice.setMergeFlowSource("feature-x");
    expect(get().mergeFlowProjectId).toBeNull();
  });

  it("setLastError is callable (synchronous)", () => {
    const { slice } = makeSlice();
    expect(() => slice.setLastError("oops")).not.toThrow();
  });
});

describe("gitSlice — mutation actions", () => {
  function makeSlice() {
    let state: any = {};
    const set = (partial: any) => {
      state = typeof partial === "function" ? { ...state, ...partial(state) } : { ...state, ...partial };
    };
    const get = () => state;
    const slice = createGitSlice(set, get, {} as any);
    state = { ...state, ...slice };
    return { slice, get };
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("loadBranches fetches /api/git/branches and populates state", async () => {
    const { slice, get } = makeSlice();
    await slice.loadBranches();
    const { api } = await import("../../lib/api");
    expect(api.gitBranches).toHaveBeenCalled();
    expect(get().branches).toBeTruthy();
    expect(get().currentBranch).toBe("main");
  });

  it("loadLog populates logCache under the branch key", async () => {
    const { slice, get } = makeSlice();
    const { api } = await import("../../lib/api");
    (api.gitLog as any).mockResolvedValueOnce([{ sha: "x", short_sha: "x", parents: [], subject: "feat: y", body: "", author_name: "", author_email: "", author_date: "", branches: [] }]);
    await slice.loadLog("main");
    expect(get().logCache.main).toHaveLength(1);
    expect(get().logLoading.main).toBe(false);
  });

  it("loadLog under <all> key when no branch supplied", async () => {
    const { slice, get } = makeSlice();
    const { api } = await import("../../lib/api");
    (api.gitLog as any).mockResolvedValueOnce([]);
    await slice.loadLog();
    expect(get().logCache["<all>"]).toEqual([]);
  });

  it("loadStatus populates state.status", async () => {
    const { slice, get } = makeSlice();
    await slice.loadStatus();
    expect(get().status).toBeTruthy();
  });

  it("commit POSTs /api/git/commit, returns sha, refreshes log", async () => {
    const { slice, get } = makeSlice();
    const sha = await slice.commit("feat: x", ["a.yaml"]);
    expect(sha).toBe("deadbee");
    // commit() clears the logCache then triggers a background refresh via
    // loadLog(currentBranch) — assert the refresh actually fired (and the
    // empty array landed under the <all> key because currentBranch is null
    // in this isolated slice).
    expect(get().lastError).toBeNull();
    const { api } = await import("../../lib/api");
    expect(api.gitCommit).toHaveBeenCalledWith({
      message: "feat: x",
      files: ["a.yaml"],
    });
    expect(api.gitLog).toHaveBeenCalled();
  });

  it("commit failure surfaces error in lastError and rejects", async () => {
    const { slice, get } = makeSlice();
    const { api } = await import("../../lib/api");
    (api.gitCommit as any).mockRejectedValueOnce(new Error("boom"));
    await expect(slice.commit("x")).rejects.toThrow(/boom/);
    expect(get().lastError).toMatch(/boom/);
  });

  it("switchBranch invalidates caches and reloads", async () => {
    const { slice, get } = makeSlice();
    await slice.switchBranch("feature");
    const { api } = await import("../../lib/api");
    expect(api.gitBranchSwitch).toHaveBeenCalledWith("feature");
    expect(get().lastError).toBeNull();
  });

  it("invalidateHistory clears log + status + branches", () => {
    const { slice, get } = makeSlice();
    // Pre-populate.
    (slice as any).logCache = { main: [] };
    (slice as any).status = { dirty: false, modified: [], staged: [], untracked: [], conflicted: [] };
    slice.invalidateHistory();
    expect(get().logCache).toEqual({});
    expect(get().status).toBeNull();
    expect(get().branches).toBeNull();
  });
});
