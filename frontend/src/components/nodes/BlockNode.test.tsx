// BlockNode top-level smoke tests.
//
// ADR-050 (#1698) rewrote BlockNode into a fixed square topology glyph.
// Behavior-specific test groups live under __tests__/BlockNode/:
//   - compactNode.test.tsx — fixed 104×104 geometry, no body config, label
//     truncation, block-kind mark.
//   - statusSurface.test.tsx — unified status surface + error/warning click.
//   - ports.test.tsx — ADR-028 §D4 dynamic-port live-update + ADR-029
//     variadic +/- min/max + port type colours/titles.
//
// This file keeps only the sanity smoke tests so a reader who opens
// BlockNode.test.tsx still sees a quick "does this thing render at all" check
// next to the component file.

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { openNativeDialogMock, renderNode } from "./__tests__/BlockNode/test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — sanity smoke", () => {
  it("renders the block label in the square body", () => {
    renderNode({ label: "My Test Block" });
    expect(screen.getByText("My Test Block")).toBeInTheDocument();
  });

  it("renders the io category mark for io blocks", () => {
    const { container } = renderNode({ category: "io" });
    // Block-kind mark for `io` is the folder emoji "📁" (U+1F4C1).
    expect(container.textContent).toContain("📁");
  });
});
