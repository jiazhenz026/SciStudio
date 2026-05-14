/**
 * ADR-036 §3.10 — TabState discriminated-union test stubs.
 *
 * SKELETON (S36): every test is ``it.skip`` and the body throws. Phase 2A
 * implementation agent (I36a) deletes the ``.skip`` and fills in the body.
 *
 * Why skip (not just throw): vitest treats a thrown test as a failure;
 * skip keeps CI green while still surfacing the test in the runner output
 * so reviewers can see what is pending.
 */

import { describe, it } from "vitest";

describe("ADR-036 TabState discriminated union (SKELETON)", () => {
  it.skip("WorkflowTab and FileTab are distinguishable by `kind`", () => {
    // Test plan (I36a):
    //   1. Build a WorkflowTab and a FileTab in TS.
    //   2. Use a switch on `tab.kind` and assert the TS exhaustiveness
    //      check passes (compile-time check; runtime asserts the right
    //      branch ran).
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("openFileTab(filePath) creates a new file tab and focuses it", () => {
    // Test plan (I36a):
    //   1. Mock the file-read API to return content + mtime + size.
    //   2. Call useAppStore.getState().openFileTab("scratch.py").
    //   3. Assert tabs.length increased by 1, activeTabId === new tab id,
    //      new tab kind === "file", filePath === "scratch.py",
    //      language === "python".
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("openFileTab on an already-open path focuses the existing tab", () => {
    // Test plan (I36a):
    //   1. Open scratch.py once.
    //   2. Call openFileTab("scratch.py") a second time.
    //   3. Assert tabs.length unchanged, activeTabId points at the same
    //      tab id from step 1.
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("openFileTab(path, {readOnly: true}) uses 'source:' id prefix", () => {
    // Test plan (I36a, also covers ADR-036 §3.4 source-view dedup):
    //   1. openFileTab("workflows/foo.yaml", {readOnly: true}).
    //   2. Assert the new tab id starts with "source:".
    //   3. Second call with same args focuses, no duplicate.
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("updateFileTabContent flips dirty true on first edit", () => {
    // Test plan (I36a):
    //   1. Open a file tab (clean).
    //   2. updateFileTabContent(id, "new content").
    //   3. Assert tab.dirty === true and tab.content === "new content".
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("saveFileTab clears dirty and updates contentLoadedAt", () => {
    // Test plan (I36a):
    //   1. Open file tab, edit, dirty=true.
    //   2. Mock PUT to return new mtime.
    //   3. await saveFileTab(id).
    //   4. Assert dirty=false and contentLoadedAt === new mtime.
    throw new Error("ADR-036 skeleton — fill in");
  });
});
