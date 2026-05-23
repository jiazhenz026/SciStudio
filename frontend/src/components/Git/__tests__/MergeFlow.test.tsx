/**
 * D39-2.4b tests for `MergeFlow.tsx`.
 *
 * Mocks `api.gitMerge` / `gitMergeComplete` / `gitMergeAbort` and asserts
 * state-machine transitions: fast-forward / clean / conflict / error,
 * plus the conflict → complete / abort branches.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MergeFlow } from "../MergeFlow";
import type * as ApiModule from "../../../lib/api";

// Mock the api module before importing the component.
vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../../lib/api");
  return {
    ...actual,
    api: {
      gitMerge: vi.fn(),
      gitMergeComplete: vi.fn(),
      gitMergeAbort: vi.fn(),
      gitMergeStageFile: vi.fn(),
    },
  };
});

// Mock window.confirm so the Abort flow proceeds without an interactive prompt.
const confirmSpy = vi.fn();

import { api } from "../../../lib/api";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  confirmSpy.mockReset();
  confirmSpy.mockReturnValue(true);
  // jsdom doesn't ship confirm by default in some setups; force it.
  window.confirm = confirmSpy;
});

describe("MergeFlow (D39-2.4b)", () => {
  it("renders nothing when isOpen=false", () => {
    const { container } = render(
      <MergeFlow sourceBranch="feature-x" isOpen={false} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("fast-forward path closes the modal after a brief toast", async () => {
    vi.useFakeTimers();
    (api.gitMerge as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: "fast-forward",
      conflicted_files: [],
    });
    const onClose = vi.fn();
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={onClose} />);
    // In-flight phase appears first.
    expect(screen.getByTestId("merge-flow-in-flight")).toBeDefined();
    // Let the promise resolve.
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    // Success phase shown.
    expect(screen.getByTestId("merge-flow-success")).toBeDefined();
    // After the 1s toast, onClose fires.
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(onClose).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("clean three-way path closes the modal after a brief toast", async () => {
    vi.useFakeTimers();
    (api.gitMerge as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: "clean",
      conflicted_files: [],
    });
    const onClose = vi.fn();
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={onClose} />);
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(screen.getByTestId("merge-flow-success")).toBeDefined();
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(onClose).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("conflict path renders ConflictResolveView with the file list", async () => {
    (api.gitMerge as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: "conflict",
      conflicted_files: ["a.py", "b.py"],
    });
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId("merge-flow-conflict")).toBeDefined();
    });
    expect(screen.getByTestId("conflict-resolve-view")).toBeDefined();
    expect(screen.getByText("a.py")).toBeDefined();
    expect(screen.getByText("b.py")).toBeDefined();
  });

  it("conflict path: Complete Merge fires gitMergeComplete when all resolved", async () => {
    const user = userEvent.setup();
    (api.gitMerge as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: "conflict",
      conflicted_files: ["a.py"],
    });
    (api.gitMergeStageFile as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "ok",
    });
    (api.gitMergeComplete as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "ok",
      commit_sha: "abc1234",
    });
    const onClose = vi.fn();
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId("merge-flow-conflict")).toBeDefined();
    });
    // Mark a.py resolved.
    await user.click(screen.getByTestId("conflict-mark-resolved-a.py"));
    await waitFor(() => {
      expect(api.gitMergeStageFile).toHaveBeenCalledWith("a.py");
    });
    // Now Complete is enabled.
    const complete = screen.getByTestId("conflict-complete-button");
    expect(complete.getAttribute("aria-disabled")).toBe("false");
    await user.click(complete);
    await waitFor(() => {
      expect(api.gitMergeComplete).toHaveBeenCalled();
    });
  });

  it("conflict path: Abort Merge fires gitMergeAbort", async () => {
    const user = userEvent.setup();
    (api.gitMerge as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: "conflict",
      conflicted_files: ["a.py"],
    });
    (api.gitMergeAbort as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "ok",
    });
    const onClose = vi.fn();
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId("merge-flow-conflict")).toBeDefined();
    });
    await user.click(screen.getByTestId("conflict-abort-button"));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(api.gitMergeAbort).toHaveBeenCalled();
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("error path: rejected gitMerge surfaces the error message", async () => {
    (api.gitMerge as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("merge engine exploded"),
    );
    const onClose = vi.fn();
    render(<MergeFlow sourceBranch="feature-x" isOpen={true} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId("merge-flow-error")).toBeDefined();
    });
    expect(screen.getByText(/merge engine exploded/)).toBeDefined();
  });
});
