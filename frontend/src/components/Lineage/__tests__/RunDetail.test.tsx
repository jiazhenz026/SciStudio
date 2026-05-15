/**
 * D39-2.5 — RunDetail Restore button tests.
 *
 * Verifies the cross-track wiring per ADR-038 §3.8 + ADR-039 §6 Phase 4:
 * clicking "Restore this run's workflow" must call ``api.gitRestore``
 * with the exact ``{commit_sha, files}`` shape, where ``files`` resolves
 * to ``workflows/<workflow_id>.yaml`` and ``commit_sha`` is the run's
 * captured ``workflow_git_commit``.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunDetail, {
  RestoreWorkflowButton,
  runRestoreWorkflow,
  workflowYamlPathForRun,
} from "../RunDetail";

vi.mock("../../../lib/api", () => ({
  api: {
    gitRestore: vi.fn().mockResolvedValue({ status: "ok" }),
  },
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
});

describe("RunDetail", () => {
  it("renders the run id and the Restore button", () => {
    render(
      <RunDetail
        run={{ run_id: "run-42", workflow_id: "main", workflow_git_commit: "abc" }}
      />,
    );
    expect(screen.getByTestId("run-detail").textContent).toContain("run-42");
    expect(screen.getByRole("button", { name: /restore this run/i })).toBeInTheDocument();
  });
});
