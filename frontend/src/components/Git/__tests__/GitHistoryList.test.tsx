/**
 * Skeleton tests for GitHistoryList (ADR-039 §3.5 line 218 + §3.4 + §3.5c).
 *
 * D39-2.3b flips each `it.skip` once the component renders the markup
 * described in GitHistoryList.tsx top docstring and wires loadLog +
 * historyFilter from gitSlice.
 */
import { describe, expect, it } from "vitest";

import { GitHistoryList } from "../GitHistoryList";

describe("ADR-039 §3.5 — GitHistoryList (skeleton)", () => {
  it("exports GitHistoryList as a function", () => {
    expect(typeof GitHistoryList).toBe("function");
  });

  it.skip("renders loading state when logLoading[branch] === true — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed store: logLoading = { main: true }, logCache = {}.
     *   2. Render <GitHistoryList branch="main" />.
     *   3. Expect `[data-testid="git-history-loading"]` present.
     */
  });

  it.skip("renders empty state when logCache[branch] === [] — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed store: logCache = { main: [] }, logLoading = { main: false }.
     *   2. Render; expect `[data-testid="git-history-empty"]` present.
     */
  });

  it.skip("renders one row per commit with short_sha + subject — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed store with 3 commits on "main".
     *   2. Render; query `[data-testid="git-history-rows"] li`.
     *   3. Expect 3 li elements with `data-testid` matching their short_sha.
     */
  });

  it.skip("filter dropdown defaults to manual and hides 'auto:' rows — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed: 3 commits — 1 with subject "feat: x", 1 with "auto: pre-run",
     *      1 with "agent: changed Y". historyFilter default ("manual").
     *   2. Render; expect ONE row visible (only the "feat:" / user commit).
     *   3. Query `[data-testid="git-history-filter"]`; expect value === "manual".
     */
  });

  it.skip("changing filter to 'all' reveals auto + agent rows — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Same seed; fireEvent.change(filter, { target: { value: "all" } }).
     *   2. Expect 3 rows rendered, each with the right data-commit-prefix.
     */
  });

  it.skip("changing filter to 'agent' shows only agent: rows — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Seed 3 commits; switch filter to "agent".
     *   2. Expect exactly the agent-prefixed row visible; check the icon
     *      span renders "🤖".
     */
  });

  it.skip("clicking a row dispatches onCommitClick — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render with onCommitClick = vi.fn();
     *   2. fireEvent.click on the first row.
     *   3. Expect onCommitClick called with that commit object.
     */
  });

  it.skip("clicking restore button dispatches onRestoreClick (stopPropagation) — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render with onCommitClick + onRestoreClick spies.
     *   2. fireEvent.click on the row's restore button.
     *   3. Expect onRestoreClick called, onCommitClick NOT called.
     */
  });

  it.skip("dispatches loadLog on mount if logCache[branch] is missing — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Spy loadLog; render <GitHistoryList branch="main" />.
     *   2. Expect loadLog called once with "main".
     */
  });

  it.skip("dispatches loadLog on branch prop change — D39-2.3b implements", () => {
    /*
     * Test plan:
     *   1. Render with branch="main"; rerender with branch="feature".
     *   2. Expect loadLog called twice, second with "feature".
     */
  });
});
