/**
 * ADR-036 §3.1 — CodeEditor component test stubs.
 *
 * SKELETON (S36): every test is ``it.skip``. Phase 2B implementation
 * agent (I36b) deletes the ``.skip`` and fills in the body.
 *
 * The non-skeleton tests will mock `@monaco-editor/react` with vi.mock so
 * the component renders in jsdom without canvas. Mirror the existing
 * pattern in ``frontend/src/components/AIChat/__tests__/TerminalView.test.tsx``
 * which mocks `@xterm/xterm` the same way.
 */

import { describe, it } from "vitest";

describe("ADR-036 CodeEditor (SKELETON)", () => {
  it.skip("renders without crashing for a Python file tab", () => {
    // Test plan (I36b):
    //   1. vi.mock('@monaco-editor/react').
    //   2. Render <CodeEditor tab={{kind:"file", language:"python", ...}} ... />.
    //   3. Assert the mock Editor was called once with value === tab.content.
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("propagates content changes via onContentChange", () => {
    // Test plan (I36b):
    //   1. Render with a vi.fn() onContentChange.
    //   2. Trigger the mocked editor's onChange("new value").
    //   3. Assert onContentChange called with "new value".
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("debounces lint requests (5 rapid edits → 1 POST after 600 ms)", () => {
    // Test plan (I36b):
    //   1. vi.useFakeTimers.
    //   2. Wire a fetch mock for /api/lint/python.
    //   3. Trigger 5 onChange calls within 100 ms.
    //   4. Advance time by 599 ms — assert no POST yet.
    //   5. Advance to 601 ms — assert exactly 1 POST.
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("renders Monaco markers from /api/lint/python response", () => {
    // Test plan (I36b):
    //   1. Mock /api/lint/python to return a single F401 diagnostic.
    //   2. Render, trigger an edit, advance timers past 600 ms.
    //   3. Assert the mocked editor's setModelMarkers was called with a
    //      marker whose code === "F401".
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("respects tab.readOnly via editor.updateOptions", () => {
    // Test plan (I36b):
    //   1. Render with tab.readOnly=true.
    //   2. Assert the mocked editor was constructed with options.readOnly === true.
    //   3. Re-render with readOnly=false; assert updateOptions called.
    throw new Error("ADR-036 skeleton — fill in");
  });

  it.skip("Ctrl+S inside the editor invokes onSave", () => {
    // Test plan (I36b):
    //   1. Render with a vi.fn() onSave.
    //   2. Simulate Ctrl+S keydown on the editor host element.
    //   3. Assert onSave called once.
    throw new Error("ADR-036 skeleton — fill in");
  });
});
