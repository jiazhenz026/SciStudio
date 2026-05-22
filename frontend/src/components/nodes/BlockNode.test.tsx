// BlockNode top-level smoke tests.
//
// Behavior-specific test groups live under __tests__/BlockNode/ after the
// #1422 god-file refactor:
//   - capabilities.test.tsx — ADR-043 format capabilities + #1307 filter +
//     hidden direction field for IO blocks.
//   - ports.test.tsx — ADR-028 §D4 dynamic port live-update + #467 Browse
//     button removal.
//   - errors.test.tsx — #422 inline error message rendering.
//   - caret.test.tsx — #710 caret preservation + audit follow-up.
//   - nativeDialog.test.tsx — #678 native-dialog status-aware fallback.
//   - hooks1420.test.tsx — #1420 InlineTextInputField hook order
//     (Wave 1) preserved through the Wave 2 split.
//
// This file keeps only the sanity smoke tests so a reader who opens
// BlockNode.test.tsx still sees a quick "does this thing render at all"
// check next to the component file.

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { openNativeDialogMock, renderNode } from "./__tests__/BlockNode/test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — sanity smoke", () => {
  it("renders the block label in the header", () => {
    renderNode({ label: "My Test Block" });
    expect(screen.getByText("My Test Block")).toBeInTheDocument();
  });

  it("renders the io category icon for io blocks", () => {
    const { container } = renderNode({ category: "io" });
    // Icon is the folder emoji "📁" (U+1F4C1) — check it appears somewhere.
    expect(container.textContent).toContain("📁");
  });
});
