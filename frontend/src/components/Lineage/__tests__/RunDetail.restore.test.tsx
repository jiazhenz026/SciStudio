/**
 * Phase 3.5 integration audit P2-3 — split-out from ADR-039 D39-2.5's
 * `RunDetail.test.tsx`. The ADR-038 full-body `RunDetail.test.tsx` and
 * the ADR-039 Restore-helpers tests both want to live next to
 * `RunDetail.tsx`, so the integration keeps two test files:
 *
 *   - `RunDetail.test.tsx`         — ADR-038 RunDetail tab body tests
 *   - `RunDetail.restore.test.tsx` — ADR-039 Restore button + helpers tests
 *
 * The obsolete D39 `describe("RunDetail")` block from the original D39
 * test file (which mounted `<RunDetail run={...} />` against a stub
 * default export) is dropped — the integrated RunDetail is a named
 * export that reads from the store; the canonical RunDetail tests live
 * in `RunDetail.test.tsx`.
 *
 * Verifies the cross-track wiring per ADR-038 §3.8 + ADR-039 §6 Phase 4:
 * clicking "Restore this run's workflow" must call ``api.gitRestore``
 * with the exact ``{commit_sha, files}`` shape, where ``files`` resolves
 * to ``workflows/<workflow_id>.yaml`` and ``commit_sha`` is the run's
 * captured ``workflow_git_commit``.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RestoreWorkflowButton, runRestoreWorkflow, workflowYamlPathForRun } from "../RunDetail";

vi.mock("../../../lib/api", () => ({
  api: {
    gitRestore: vi.fn().mockResolvedValue({ status: "ok", auto_commit_sha: null }),
  },
  setWorkflowWriteStartedListener: vi.fn(),
}));

import { api } from "../../../lib/api";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("workflowYamlPathForRun", () => {
  it("returns the canonical workflows/<id>.yaml relative path", () => {
    expect(workflowYamlPathForRun({ workflow_id: "main" })).toBe("workflows/main.yaml");
    expect(workflowYamlPathForRun({ workflow_id: "image_pipeline" })).toBe(
      "workflows/image_pipeline.yaml",
    );
  });
});

describe("runRestoreWorkflow", () => {
  it("calls api.gitRestore with the captured SHA and YAML file scope", async () => {
    await runRestoreWorkflow({
      run_id: "r1",
      workflow_id: "main",
      workflow_git_commit: "abc123def456",
    });
    expect(api.gitRestore).toHaveBeenCalledWith({
      commit_sha: "abc123def456",
      files: ["workflows/main.yaml"],
    });
  });

  it("throws and skips the API call when workflow_git_commit is null", async () => {
    await expect(
      runRestoreWorkflow({ run_id: "r1", workflow_id: "main", workflow_git_commit: null }),
    ).rejects.toThrow(/no recorded git commit/i);
    expect(api.gitRestore).not.toHaveBeenCalled();
  });
});

describe("RestoreWorkflowButton", () => {
  it("renders enabled when workflow_git_commit is present", () => {
    render(
      <RestoreWorkflowButton
        run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: "abc" }}
      />,
    );
    const btn = screen.getByRole("button", { name: /restore this run/i });
    expect(btn).not.toBeDisabled();
  });

  it("renders disabled when workflow_git_commit is null", () => {
    render(
      <RestoreWorkflowButton
        run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: null }}
      />,
    );
    const btn = screen.getByRole("button", { name: /restore this run/i });
    expect(btn).toBeDisabled();
  });

  it("on click, dispatches gitRestore with the right args and fires onRestored", async () => {
    const onRestored = vi.fn();
    render(
      <RestoreWorkflowButton
        run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: "deadbeef1234" }}
        onRestored={onRestored}
      />,
    );
    const btn = screen.getByRole("button", { name: /restore this run/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(api.gitRestore).toHaveBeenCalledWith({
        commit_sha: "deadbeef1234",
        files: ["workflows/main.yaml"],
      });
      expect(onRestored).toHaveBeenCalledTimes(1);
    });
  });

  it("on click with auto_commit_sha present, surfaces 'committed as <sha>' hint and NO stash language (ADR-039 Addendum 1 / #1354)", async () => {
    // Re-prime the mock to return an auto-commit SHA.
    (api.gitRestore as any).mockResolvedValueOnce({
      status: "ok",
      auto_commit_sha: "ab12345deadbeef" + "0".repeat(25),
    });
    render(
      <RestoreWorkflowButton
        run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: "deadbeef1234" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /restore this run/i }));
    await waitFor(() => {
      const hint = screen.getByTestId("run-detail-restore-auto-commit-hint");
      expect(hint.textContent ?? "").toMatch(
        /Your unsaved changes were committed as ab12345 before the restore — see History tab to revert if unintended/,
      );
      // The pre-addendum amber "stashed as ..." hint must not appear.
      expect(hint.textContent ?? "").not.toMatch(/stash/i);
    });
    // Old stash-hint testid must not be in the DOM either.
    expect(screen.queryByTestId("run-detail-restore-stash-hint")).toBeNull();
  });

  it("on click with auto_commit_sha=null, no auto-commit hint renders (clean tree)", async () => {
    (api.gitRestore as any).mockResolvedValueOnce({
      status: "ok",
      auto_commit_sha: null,
    });
    render(
      <RestoreWorkflowButton
        run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: "deadbeef1234" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /restore this run/i }));
    await waitFor(() => {
      expect(api.gitRestore).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("run-detail-restore-auto-commit-hint")).toBeNull();
  });
});
