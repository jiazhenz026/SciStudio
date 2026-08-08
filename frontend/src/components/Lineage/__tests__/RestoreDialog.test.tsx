/**
 * `RestoreDialog` — ADR-038 Addendum 1 §11.5 (#2033).
 *
 * The tests that matter most here are the ones about *distinguishing states*.
 * The dialog this replaces had one failure mode that mattered: it collapsed
 * "no drift found", "nothing was checked", and "the check failed" into a
 * single green "No drift detected" banner. Because its endpoint never existed,
 * every user who ever opened it saw that banner, and it was never true.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RestoreDialog } from "../RestoreDialog";

vi.mock("../../../lib/api", () => ({
  api: {
    gitRestore: vi.fn().mockResolvedValue({ status: "ok", auto_commit_sha: null }),
    lineage: { validateRestore: vi.fn() },
  },
  setWorkflowWriteStartedListener: vi.fn(),
}));

import { api } from "../../../lib/api";

const CLEAN = {
  commit_sha: "abc1234",
  run_id: "run-1",
  run_started_at: "2026-05-15T14:30:00Z",
  input_warnings: [],
  env_warnings: [],
};

function mockPreflight(value: unknown) {
  (
    api.lineage.validateRestore as unknown as { mockResolvedValue: (v: unknown) => void }
  ).mockResolvedValue(value);
}

function mockPreflightRejection(err: Error) {
  (
    api.lineage.validateRestore as unknown as { mockRejectedValue: (v: unknown) => void }
  ).mockRejectedValue(err);
}

async function renderDialog(onClose = vi.fn(), onRestored?: (sha: string | null) => void) {
  render(
    <RestoreDialog
      commitSha="abc1234"
      targetLabel="15 May 2026, 14:30"
      onClose={onClose}
      onRestored={onRestored}
    />,
  );
  await waitFor(() => {
    expect(screen.queryByTestId("restore-dialog-loading")).not.toBeInTheDocument();
  });
}

beforeEach(() => {
  mockPreflight(CLEAN);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RestoreDialog preflight target", () => {
  it("passes the run id through when the caller has one", async () => {
    render(
      <RestoreDialog
        commitSha="abc1234"
        targetLabel="15 May 2026, 14:30"
        runId="run-1"
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(api.lineage.validateRestore).toHaveBeenCalledWith("abc1234", "run-1");
    });
  });

  it("omits it for a bare commit (the Git tab has no run)", async () => {
    await renderDialog();
    expect(api.lineage.validateRestore).toHaveBeenCalledWith("abc1234", undefined);
  });
});

describe("RestoreDialog scope disclosure", () => {
  it("states that the whole project is restored, not just the workflow", async () => {
    await renderDialog();
    const text = screen.getByTestId("restore-dialog").textContent ?? "";
    expect(text).toMatch(/whole project/i);
    expect(text).toMatch(/custom blocks/i);
  });

  it("states that data files and the environment are not restored", async () => {
    await renderDialog();
    const text = screen.getByTestId("restore-dialog").textContent ?? "";
    expect(text).toMatch(/data files are left alone/i);
    expect(text).toMatch(/software environment/i);
  });
});

describe("RestoreDialog preflight states", () => {
  it("renders the clean banner only when a run was found and nothing moved", async () => {
    await renderDialog();
    expect(screen.getByTestId("restore-dialog-preflight-clean")).toBeInTheDocument();
  });

  it("does NOT render the clean banner when no run is recorded at the commit", async () => {
    mockPreflight({ ...CLEAN, run_id: null });
    await renderDialog();
    expect(screen.queryByTestId("restore-dialog-preflight-clean")).not.toBeInTheDocument();
    const unknown = screen.getByTestId("restore-dialog-preflight-unknown");
    expect(unknown.textContent ?? "").toMatch(/nothing to compare/i);
  });

  it("does NOT render the clean banner when the preflight request failed", async () => {
    mockPreflightRejection(new Error("network down"));
    await renderDialog();
    expect(screen.queryByTestId("restore-dialog-preflight-clean")).not.toBeInTheDocument();
    const failed = screen.getByTestId("restore-dialog-preflight-failed");
    expect(failed.textContent ?? "").toMatch(/could not check/i);
  });

  it("lists environment drift and says restore will not undo it", async () => {
    mockPreflight({
      ...CLEAN,
      env_warnings: [{ package: "numpy", old: "1.26.4", new: "2.1.0" }],
    });
    await renderDialog();
    const card = screen.getByTestId("restore-dialog-env-warnings");
    expect(card.textContent ?? "").toMatch(/numpy/);
    expect(card.textContent ?? "").toMatch(/1\.26\.4/);
    expect(card.textContent ?? "").toMatch(/2\.1\.0/);
    expect(card.textContent ?? "").toMatch(/does not roll these back/i);
  });

  it("lists changed input files", async () => {
    mockPreflight({
      ...CLEAN,
      input_warnings: [{ path: "data/in.csv", reason: "no longer exists" }],
    });
    await renderDialog();
    const card = screen.getByTestId("restore-dialog-input-warnings");
    expect(card.textContent ?? "").toMatch(/data\/in\.csv/);
    expect(card.textContent ?? "").toMatch(/no longer exists/);
  });

  it("never blocks the restore — warnings are advisory", async () => {
    mockPreflight({
      ...CLEAN,
      env_warnings: [{ package: "numpy", old: "1.26.4", new: "2.1.0" }],
      input_warnings: [{ path: "data/in.csv", reason: "no longer exists" }],
    });
    await renderDialog();
    expect(screen.getByTestId("restore-dialog-confirm")).not.toBeDisabled();
  });

  it("still allows the restore when the preflight itself failed", async () => {
    mockPreflightRejection(new Error("network down"));
    await renderDialog();
    expect(screen.getByTestId("restore-dialog-confirm")).not.toBeDisabled();
  });
});

describe("RestoreDialog confirm", () => {
  it("restores the full tree — no `files` scope", async () => {
    await renderDialog();
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      expect(api.gitRestore).toHaveBeenCalledWith({ commit_sha: "abc1234" });
    });
  });

  it("passes the auto-commit SHA to onRestored", async () => {
    (
      api.gitRestore as unknown as { mockResolvedValueOnce: (v: unknown) => void }
    ).mockResolvedValueOnce({
      status: "ok",
      auto_commit_sha: "feed1234",
    });
    const onRestored = vi.fn();
    await renderDialog(vi.fn(), onRestored);
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      expect(onRestored).toHaveBeenCalledWith("feed1234");
    });
  });

  it("keeps the dialog open and shows the error when the restore fails", async () => {
    (
      api.gitRestore as unknown as { mockRejectedValueOnce: (v: unknown) => void }
    ).mockRejectedValueOnce(new Error("commit not found"));
    const onClose = vi.fn();
    await renderDialog(onClose);
    fireEvent.click(screen.getByTestId("restore-dialog-confirm"));
    await waitFor(() => {
      expect(screen.getByTestId("restore-dialog-submit-error").textContent ?? "").toMatch(
        /commit not found/,
      );
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on cancel without restoring", async () => {
    const onClose = vi.fn();
    await renderDialog(onClose);
    fireEvent.click(screen.getByTestId("restore-dialog-cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(api.gitRestore).not.toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    await renderDialog(onClose);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
