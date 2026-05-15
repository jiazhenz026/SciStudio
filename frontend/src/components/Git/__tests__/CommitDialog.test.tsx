/**
 * D39-2.3b — CommitDialog tests.
 *
 * Verifies the dialog renders the template, file list, handles validation,
 * and dispatches gitSlice.commit. Mirrors the data-testid contract baked
 * into the component's top docstring.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CommitDialog,
  COMMIT_TEMPLATE,
  formatAutoDetectedFiles,
  stripCommentLines,
} from "../CommitDialog";
import { useAppStore } from "../../../store";
import { ApiError } from "../../../lib/api";
import type { GitStatus } from "../../../types/api";

const cleanStatus: GitStatus = {
  dirty: false,
  modified: [],
  staged: [],
  untracked: [],
  conflicted: [],
};

const dirtyStatus: GitStatus = {
  dirty: true,
  modified: ["workflows/a.yaml"],
  staged: ["blocks/b.py"],
  untracked: ["notes/c.md"],
  conflicted: [],
};

function seedStore(overrides: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({
    status: dirtyStatus,
    loadStatus: vi.fn().mockResolvedValue(undefined),
    commit: vi.fn().mockResolvedValue("abcdef0"),
    ...overrides,
  });
}

beforeEach(() => {
  seedStore();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CommitDialog — pure helpers", () => {
  it("COMMIT_TEMPLATE matches ADR §3.5 line 230 shape (subject + comment list)", () => {
    expect(COMMIT_TEMPLATE.startsWith("<one-line subject>")).toBe(true);
    expect(COMMIT_TEMPLATE).toContain("# What changed:");
  });

  it("stripCommentLines drops lines starting with '#' and trims", () => {
    const raw = `feat: add cellpose block

# Auto-detected modified files:
#   M  workflows/x.yaml
`;
    expect(stripCommentLines(raw)).toBe("feat: add cellpose block");
  });

  it("stripCommentLines returns empty string for an all-comment input", () => {
    const raw = "# only comments\n# more\n";
    expect(stripCommentLines(raw)).toBe("");
  });

  it("formatAutoDetectedFiles returns empty string when status is null", () => {
    expect(formatAutoDetectedFiles(null)).toBe("");
  });

  it("formatAutoDetectedFiles emits per-file lines with M/S/A markers", () => {
    const out = formatAutoDetectedFiles(dirtyStatus);
    expect(out).toContain("M  workflows/a.yaml");
    expect(out).toContain("S  blocks/b.py");
    expect(out).toContain("A  notes/c.md");
  });
});

describe("CommitDialog — UI", () => {
  it("returns null when open=false", () => {
    const { container } = render(<CommitDialog open={false} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders dialog and textarea placeholder starts with the template", () => {
    render(<CommitDialog open={true} onClose={() => {}} />);
    const ta = screen.getByTestId("commit-dialog-message") as HTMLTextAreaElement;
    expect(ta.placeholder.startsWith("<one-line subject>")).toBe(true);
  });

  it("renders the auto-detected file list from gitSlice.status", () => {
    render(<CommitDialog open={true} onClose={() => {}} />);
    const list = screen.getByTestId("commit-dialog-files");
    expect(list.textContent).toContain("workflows/a.yaml");
    expect(list.textContent).toContain("blocks/b.py");
    expect(list.textContent).toContain("notes/c.md");
  });

  it("disables Submit when status is clean (no changes to commit)", () => {
    seedStore({ status: cleanStatus });
    render(<CommitDialog open={true} onClose={() => {}} />);
    const submit = screen.getByTestId("commit-dialog-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("disables Submit when stripped message is empty", () => {
    render(<CommitDialog open={true} onClose={() => {}} />);
    const ta = screen.getByTestId("commit-dialog-message");
    fireEvent.change(ta, { target: { value: "# only a comment\n\n" } });
    const submit = screen.getByTestId("commit-dialog-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("calls gitSlice.commit with stripped message + initialFiles on submit", async () => {
    const commit = vi.fn().mockResolvedValue("abcdef0");
    seedStore({ commit });
    const onClose = vi.fn();
    render(
      <CommitDialog
        open={true}
        onClose={onClose}
        initialFiles={["workflows/a.yaml"]}
      />,
    );
    fireEvent.change(screen.getByTestId("commit-dialog-message"), {
      target: { value: "feat: x\n# comment\n" },
    });
    fireEvent.click(screen.getByTestId("commit-dialog-submit"));
    await waitFor(() => expect(commit).toHaveBeenCalledWith("feat: x", ["workflows/a.yaml"]));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("shows server error inline on commit failure and does not close", async () => {
    const commit = vi.fn().mockRejectedValue(new ApiError("nothing to commit", 409));
    seedStore({ commit });
    const onClose = vi.fn();
    render(<CommitDialog open={true} onClose={onClose} />);
    fireEvent.change(screen.getByTestId("commit-dialog-message"), {
      target: { value: "feat: x" },
    });
    fireEvent.click(screen.getByTestId("commit-dialog-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("commit-dialog-error").textContent).toMatch(/nothing to commit/i);
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("Cancel button calls onClose", () => {
    const onClose = vi.fn();
    render(<CommitDialog open={true} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("commit-dialog-cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Ctrl+Enter on the dialog submits", async () => {
    const commit = vi.fn().mockResolvedValue("abc");
    seedStore({ commit });
    render(<CommitDialog open={true} onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("commit-dialog-message"), {
      target: { value: "feat: y" },
    });
    fireEvent.keyDown(screen.getByTestId("commit-dialog"), {
      key: "Enter",
      ctrlKey: true,
    });
    await waitFor(() => expect(commit).toHaveBeenCalled());
  });
});
