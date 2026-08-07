/**
 * Restore button + dialog wiring — ADR-038 Addendum 1 §11.5 (#2033).
 *
 * Rewritten from the ADR-039 §6 Phase 4 version of this file. That version
 * asserted the exact defect this issue removes: that clicking Restore called
 * `api.gitRestore` with `files: ["workflows/<id>.yaml"]`. Scoping the restore
 * to the workflow YAML is why a user who had broken a custom block could
 * restore the run that worked and hit the same failure — the graph came back,
 * the block source did not.
 *
 * What is asserted now:
 *
 *   - the button opens the confirmation dialog rather than restoring on click;
 *   - confirming restores the FULL TREE (no `files` key at all);
 *   - the ADR-038 §3.6 preflight runs against the run's commit;
 *   - the degraded-run guard (`workflow_git_commit === null` → disabled)
 *     survives the rewrite;
 *   - the auto-commit recovery hint still surfaces (ADR-039 Addendum 1 / #1354).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RestoreRunButton, restoreTargetLabel } from "../RunDetail";

vi.mock("../../../lib/api", () => ({
  api: {
    gitRestore: vi.fn().mockResolvedValue({ status: "ok", auto_commit_sha: null }),
    lineage: {
      validateRestore: vi.fn().mockResolvedValue({
        commit_sha: "deadbeef1234",
        run_id: "r1",
        run_started_at: "2026-05-15T14:30:00Z",
        input_warnings: [],
        env_warnings: [],
      }),
    },
  },
  setWorkflowWriteStartedListener: vi.fn(),
}));

import { api } from "../../../lib/api";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const ANCHORED = {
  run_id: "r1",
  workflow_id: "main",
  workflow_git_commit: "deadbeef1234",
  started_at: "2026-05-15T14:30:00Z",
};

async function openDialog(run = ANCHORED, onRestored?: () => void) {
  render(<RestoreRunButton run={run} onRestored={onRestored} />);
  fireEvent.click(screen.getByTestId("run-detail-restore-button"));
  await waitFor(() => {
    expect(screen.getByTestId("restore-dialog")).toBeInTheDocument();
  });
}

describe("restoreTargetLabel", () => {
  it("prefers the run's start time", () => {
    const label = restoreTargetLabel(ANCHORED);
    expect(label).toBe(new Date("2026-05-15T14:30:00Z").toLocaleString());
  });

  it("falls back to a short run id when the row has no timestamp", () => {
    expect(
      restoreTargetLabel({ run_id: "abcdef123456", workflow_id: "m", workflow_git_commit: "x" }),
    ).toBe("run abcdef12");
  });
});

describe("RestoreRunButton", () => {
  it("is labelled 'Restore', not 'Restore workflow'", () => {
    render(<RestoreRunButton run={ANCHORED} />);
    const btn = screen.getByTestId("run-detail-restore-button");
    expect(btn.textContent).toBe("Restore");
  });

  it("renders disabled when workflow_git_commit is null (degraded run)", () => {
    render(
      <RestoreRunButton run={{ run_id: "r1", workflow_id: "main", workflow_git_commit: null }} />,
    );
    expect(screen.getByTestId("run-detail-restore-button")).toBeDisabled();
  });

  it("opens the confirmation dialog instead of restoring immediately", async () => {
    await openDialog();
    expect(api.gitRestore).not.toHaveBeenCalled();
  });

  it("runs the ADR-038 §3.6 preflight against the run's commit AND its run id", async () => {
    // Codex P2 on PR #2034: several runs can share one commit — the pre-run
    // auto-commit is skipped on an already-clean tree — so passing only the
    // SHA lets the backend compare against the newest run at it, which may be
    // a later failure rather than the run the user picked.
    await openDialog();
    expect(api.lineage.validateRestore).toHaveBeenCalledWith("deadbeef1234", "r1");
  });

  it("confirming restores the FULL TREE — no `files` scope", async () => {
    const onRestored = vi.fn();
    await openDialog(ANCHORED, onRestored);
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      expect(api.gitRestore).toHaveBeenCalledWith({ commit_sha: "deadbeef1234" });
      expect(onRestored).toHaveBeenCalledTimes(1);
    });
    // The pre-#2033 single-YAML scope must not come back.
    const callArg = (api.gitRestore as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0][0];
    expect(callArg).not.toHaveProperty("files");
  });

  it("cancelling closes the dialog without restoring", async () => {
    await openDialog();
    fireEvent.click(screen.getByTestId("restore-dialog-cancel"));
    await waitFor(() => {
      expect(screen.queryByTestId("restore-dialog")).not.toBeInTheDocument();
    });
    expect(api.gitRestore).not.toHaveBeenCalled();
  });

  it("surfaces the auto-commit recovery hint, with no stash language", async () => {
    (
      api.gitRestore as unknown as { mockResolvedValueOnce: (v: unknown) => void }
    ).mockResolvedValueOnce({
      status: "ok",
      auto_commit_sha: "ab12345deadbeef" + "0".repeat(25),
    });
    await openDialog();
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      const hint = screen.getByTestId("run-detail-restore-auto-commit-hint");
      expect(hint.textContent ?? "").toMatch(/committed as ab12345 before the restore/);
      expect(hint.textContent ?? "").not.toMatch(/stash/i);
    });
  });

  it("renders no hint when the tree was already clean", async () => {
    await openDialog();
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      expect(api.gitRestore).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("run-detail-restore-auto-commit-hint")).toBeNull();
  });
});
