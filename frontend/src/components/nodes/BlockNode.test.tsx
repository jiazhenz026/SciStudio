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
  it("renders the block label", () => {
    // ADR-050 canvas polish (#1698): the label renders below the square body.
    renderNode({ label: "My Test Block" });
    expect(screen.getByTestId("block-node-label")).toHaveTextContent("My Test Block");
  });

  it("renders a category icon (lucide svg) for io blocks", () => {
    const { container } = renderNode({ category: "io" });
    // ADR-050 canvas polish (#1698): the block-kind mark is now a lucide line
    // icon (an <svg>) in the body, not an emoji text node.
    const body = container.querySelector('[data-testid="block-node-body"]');
    expect(body?.querySelector("svg")).not.toBeNull();
  });
});
