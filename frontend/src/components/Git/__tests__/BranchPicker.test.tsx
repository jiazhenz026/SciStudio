/**
 * Skeleton tests for BranchPicker (ADR-039 §3.5 line 221 + §3.7).
 *
 * D39-2.3b flips each `it.skip` once the dropdown renders the markup
 * described in BranchPicker.tsx top docstring and wires loadBranches +
 * switchBranch from gitSlice.
 */
import { describe, expect, it } from "vitest";

import { BranchPicker } from "../BranchPicker";

describe("ADR-039 §3.5 / §3.7 — BranchPicker (skeleton)", () => {
  it("exports BranchPicker as a function", () => {
    expect(typeof BranchPicker).toBe("function");
  });

  it.skip("trigger label shows currentBranch name — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed store: currentBranch="main", branches=[{name:"main",is_current:true},...]
     *   2. Render; expect `[data-testid="branch-picker-trigger"]` text contains "main".
     */
  });

  it.skip("trigger label falls back to 'no branch' when currentBranch is null — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed store: currentBranch=null.
     *   2. Render; expect trigger text contains "no branch".
     */
  });

  it.skip("renders one menu item per branch with checkmark on current — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed branches=[
     *        {name:"main", is_current:true},
     *        {name:"experiment-1", is_current:false},
     *      ].
     *   2. Open the dropdown.
     *   3. Expect TWO `[data-testid^="branch-picker-item-"]` items.
     *   4. Expect the "main" item's check span shows "✓".
     */
  });

  it.skip("clicking a non-current branch calls gitSlice.switchBranch — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Mock useAppStore.switchBranch = vi.fn().mockResolvedValue();
     *   2. Render; open dropdown; click `branch-picker-item-experiment-1`.
     *   3. Expect switchBranch called with "experiment-1".
     */
  });

  it.skip("current branch item is disabled — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Open dropdown; query `branch-picker-item-main` (is_current).
     *   2. Expect aria-disabled="true" / disabled attribute.
     */
  });

  it.skip("'Create branch…' menu item calls onCreateBranchRequested — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render with onCreateBranchRequested = vi.fn();
     *   2. Click `[data-testid="branch-picker-create"]`.
     *   3. Expect prop called once.
     */
  });

  it.skip("merge submenu lists non-current branches only — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Same 2-branch seed; open merge submenu.
     *   2. Expect ONLY `branch-picker-merge-experiment-1` rendered (main excluded).
     */
  });

  it.skip("clicking merge submenu item calls onMergeRequested — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. onMergeRequested = vi.fn(); click `branch-picker-merge-experiment-1`.
     *   2. Expect prop called with "experiment-1".
     */
  });

  it.skip("dispatches loadBranches on mount — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Spy loadBranches; render.
     *   2. Expect loadBranches called once.
     */
  });

  it.skip("aria-label on trigger reflects current branch — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed currentBranch="experiment-1".
     *   2. Render; expect trigger has aria-label="Current branch: experiment-1".
     */
  });
});
