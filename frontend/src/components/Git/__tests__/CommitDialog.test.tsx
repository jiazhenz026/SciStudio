/**
 * Skeleton tests for CommitDialog (ADR-039 §3.5 line 217).
 *
 * D39-2.3b flips each `it.skip` into `it` after wiring the component to
 * gitSlice.commit + rendering the dialog markup described in the
 * CommitDialog.tsx top docstring.
 */
import { describe, expect, it } from "vitest";

import {
  CommitDialog,
  COMMIT_TEMPLATE,
  formatAutoDetectedFiles,
  stripCommentLines,
} from "../CommitDialog";

describe("ADR-039 §3.5 — CommitDialog (skeleton)", () => {
  it("exports CommitDialog as a function", () => {
    expect(typeof CommitDialog).toBe("function");
  });

  it("COMMIT_TEMPLATE matches ADR §3.5 line 230 shape (subject + comment list)", () => {
    // The placeholder shown in the textarea begins with the one-line
    // subject hint, then a `# What changed:` block — keep this assertion
    // strict so D39-2.3b cannot silently drift from the ADR.
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
    const out = formatAutoDetectedFiles({
      dirty: true,
      modified: ["workflows/a.yaml"],
      staged: ["blocks/b.py"],
      untracked: ["notes/c.md"],
      conflicted: [],
    });
    expect(out).toContain("M  workflows/a.yaml");
    expect(out).toContain("S  blocks/b.py");
    expect(out).toContain("A  notes/c.md");
  });

  it.skip("renders dialog with default template in textarea — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render <CommitDialog open={true} onClose={vi.fn()} />.
     *   2. Query `[data-testid="commit-dialog-message"]`.
     *   3. Expect its placeholder starts with COMMIT_TEMPLATE.
     */
  });

  it.skip("renders auto-detected file list from gitSlice.status — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed useAppStore with status = {dirty:true, modified:["a.yaml"], ...}.
     *   2. Render the dialog.
     *   3. Query `[data-testid="commit-dialog-files"]` and assert each file
     *      appears once.
     */
  });

  it.skip("disables submit when stripped message is empty — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render dialog; query submit button.
     *   2. Set textarea to comments-only.
     *   3. Expect submit `disabled` attr is true.
     */
  });

  it.skip("calls gitSlice.commit with stripped message + initialFiles — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Mock useAppStore.commit = vi.fn().mockResolvedValue("sha");
     *   2. Render with initialFiles=["x.yaml"]; type a message; click submit.
     *   3. Expect commit() called with (strippedMessage, ["x.yaml"]).
     */
  });

  it.skip("keeps dialog open and shows server error on 409 — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Mock commit() to reject with ApiError("nothing to commit", 409).
     *   2. Click submit.
     *   3. Expect dialog still rendered AND
     *      `[data-testid="commit-dialog-error"]` contains "nothing to commit".
     */
  });

  it.skip("Esc key closes dialog — D39-2.3b implements", () => {
    // Type plan: press Escape; expect onClose called once.
  });

  it.skip("Ctrl+Enter submits the dialog — D39-2.3b implements", () => {
    // Type plan: focus textarea; press Ctrl+Enter; expect commit() called.
  });
});
