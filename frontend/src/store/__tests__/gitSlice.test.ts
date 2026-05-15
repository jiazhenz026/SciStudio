/**
 * Skeleton tests for gitSlice (ADR-039 §6 Phase 2).
 *
 * Pure-helper exports (classifyPrefix, selectVisibleCommits) are tested
 * for real here — they are safe to keep in the skeleton phase. The
 * mutation actions throw `Error("TODO: D39-2.3b — ...")` so the .skip
 * tests below remain skipped until D39-2.3b lands.
 */
import { describe, expect, it } from "vitest";

import { classifyPrefix, createGitSlice, selectVisibleCommits } from "../gitSlice";
import type { GitCommit } from "../../types/api";

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

  it("setLastError is callable (synchronous)", () => {
    const { slice } = makeSlice();
    expect(() => slice.setLastError("oops")).not.toThrow();
  });
});

describe("gitSlice — mutation actions (skeleton)", () => {
  function makeSlice() {
    let state: any = {};
    const set = (partial: any) => {
      state = typeof partial === "function" ? { ...state, ...partial(state) } : { ...state, ...partial };
    };
    const get = () => state;
    const slice = createGitSlice(set, get, {} as any);
    return slice;
  }

  it.skip("loadBranches fetches /api/git/branches — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Spy api.gitBranches; call slice.loadBranches().
     *   2. Expect state.branches matches the mocked response.
     */
  });

  it.skip("commit POSTs /api/git/commit and refreshes log — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Mock api.gitCommit + api.gitLog.
     *   2. Call slice.commit("feat: x").
     *   3. Expect gitCommit + gitLog both called; state.logCache invalidated.
     */
  });

  it("mutation methods throw a TODO error during skeleton phase", async () => {
    const slice = makeSlice();
    await expect(slice.loadBranches()).rejects.toThrow(/D39-2.3b/);
    await expect(slice.loadLog()).rejects.toThrow(/D39-2.3b/);
    await expect(slice.commit("x")).rejects.toThrow(/D39-2.3b/);
    await expect(slice.switchBranch("x")).rejects.toThrow(/D39-2.3b/);
  });
});
