// Unit tests for the canvas node hover-detail anchor geometry (#1887).

import { describe, expect, it } from "vitest";

import {
  NODE_DETAIL_POPOVER_GAP,
  NODE_DETAIL_POPOVER_MAX_HEIGHT,
  NODE_DETAIL_POPOVER_WIDTH,
  computeNodeDetailAnchor,
} from "./nodeDetailAnchor";

const VIEWPORT = { width: 1280, height: 800 };

describe("computeNodeDetailAnchor", () => {
  it("anchors to the right of the node when it fits", () => {
    const rect = { left: 200, right: 304, top: 150 };
    const anchor = computeNodeDetailAnchor(rect, VIEWPORT);
    expect(anchor.left).toBe(rect.right + NODE_DETAIL_POPOVER_GAP);
    expect(anchor.top).toBe(150);
  });

  it("flips to the left of the node when the right side would overflow", () => {
    // Node hugging the right edge: right + gap + width exceeds the viewport.
    const rect = { left: 1180, right: 1260, top: 150 };
    const anchor = computeNodeDetailAnchor(rect, VIEWPORT);
    expect(anchor.left).toBe(rect.left - NODE_DETAIL_POPOVER_GAP - NODE_DETAIL_POPOVER_WIDTH);
    expect(anchor.left).toBeGreaterThanOrEqual(NODE_DETAIL_POPOVER_GAP);
  });

  it("never runs off the left edge when flipping for a node near the left", () => {
    // Pathologically wide-but-left node so the flipped left would be negative.
    const rect = { left: 4, right: 1270, top: 150 };
    const anchor = computeNodeDetailAnchor(rect, VIEWPORT);
    expect(anchor.left).toBe(NODE_DETAIL_POPOVER_GAP);
  });

  it("clamps the top so a node near the bottom edge stays fully visible", () => {
    const rect = { left: 200, right: 304, top: 790 };
    const anchor = computeNodeDetailAnchor(rect, VIEWPORT);
    expect(anchor.top).toBe(VIEWPORT.height - NODE_DETAIL_POPOVER_MAX_HEIGHT);
  });

  it("clamps the top to the gap for a node above the viewport top", () => {
    const rect = { left: 200, right: 304, top: -50 };
    const anchor = computeNodeDetailAnchor(rect, VIEWPORT);
    expect(anchor.top).toBe(NODE_DETAIL_POPOVER_GAP);
  });
});
