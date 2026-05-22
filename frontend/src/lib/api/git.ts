/**
 * ADR-039 §3.5 — Git versioning REST surface.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422). Wraps the routes
 * registered by `src/scistudio/api/routes/git.py` (PR #927). These are
 * TYPED but otherwise straight passthroughs — no client-side semantics
 * live here.
 *
 * Wire contract reference: see `frontend/src/types/api.ts` for the
 * GitCommit / GitBranch / GitStatus / GitMergeResult shapes.
 */

import type {
  GitBranch,
  GitCommit,
  GitCommitResponse,
  GitDiff,
  GitMergeResult,
  GitRestoreResult,
  GitStatus,
} from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const gitApi = {
  gitCommit: (body: { message: string; author?: string; files?: string[] }) =>
    apiFetch<GitCommitResponse>("/api/git/commit", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  gitLog: (params?: { branch?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.branch) search.set("branch", params.branch);
    if (typeof params?.limit === "number") search.set("limit", String(params.limit));
    const qs = search.toString();
    return apiFetch<GitCommit[]>(`/api/git/log${qs ? `?${qs}` : ""}`);
  },
  gitDiff: (params: { from: string; to?: string; file?: string }) => {
    const search = new URLSearchParams();
    search.set("from", params.from);
    if (params.to) search.set("to", params.to);
    if (params.file) search.set("file", params.file);
    return apiFetch<GitDiff>(`/api/git/diff?${search.toString()}`);
  },
  gitRestore: (body: { commit_sha: string; files?: string[] }) =>
    apiFetch<GitRestoreResult>("/api/git/restore", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),

  // Branches
  gitBranches: () => apiFetch<GitBranch[]>("/api/git/branches"),
  gitBranchSwitch: (branch_name: string) =>
    apiFetch<{
      status: string;
      current_branch: string;
      auto_commit_sha: string | null;
    }>("/api/git/branch/switch", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ branch_name }),
    }),
  gitBranchCreate: (body: { name: string; base_sha?: string }) =>
    apiFetch<{ status: string; name: string }>("/api/git/branch/create", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  gitBranchDelete: (name: string, force = false) =>
    apiFetch<{ status: string }>(
      `/api/git/branches/${encodeURIComponent(name)}${force ? "?force=true" : ""}`,
      { method: "DELETE" },
    ),

  // Status
  gitStatus: () => apiFetch<GitStatus>("/api/git/status"),

  // Merge / cherry-pick
  gitMerge: (source_branch: string) =>
    apiFetch<GitMergeResult>("/api/git/merge", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ source_branch }),
    }),
  gitCherryPick: (commit_sha: string) =>
    apiFetch<GitMergeResult>("/api/git/cherry-pick", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ commit_sha }),
    }),

  // Conflict-resolution finalization (consumed by MergeFlow in D39-2.4a)
  gitMergeStageFile: (file: string) =>
    apiFetch<{ status: string }>("/api/git/merge/stage-file", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ file }),
    }),
  gitMergeComplete: () =>
    apiFetch<{ status: string; commit_sha: string }>("/api/git/merge/complete", {
      method: "POST",
      headers: JSON_HEADERS,
    }),
  gitMergeAbort: () =>
    apiFetch<{ status: string }>("/api/git/merge/abort", {
      method: "POST",
      headers: JSON_HEADERS,
    }),
};
