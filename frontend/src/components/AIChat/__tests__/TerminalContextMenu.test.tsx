/**
 * Tests that TerminalContextMenu actually wires its measurement to the
 * placement maths (#1994 follow-up).
 *
 * menuPlacement.test.ts covers the arithmetic. This file covers the part that
 * can still be wrong when the arithmetic is right: reading the menu's own size
 * and the frame's inner size, before paint, and applying the result. jsdom
 * reports 0×0 for everything, so the dimensions are stubbed explicitly.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TerminalContextMenu } from "../TerminalView.parts/TerminalContextMenu";

const MENU_WIDTH = 128;
const MENU_HEIGHT = 64;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/**
 * Give jsdom the layout numbers it does not compute: a fixed menu size, and a
 * frame that reports its inner size and is returned as the menu's offsetParent
 * (which is what the component measures against).
 */
function renderMenuInFrame(
  x: number,
  y: number,
  frame: { width: number; height: number } = { width: 800, height: 400 },
) {
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(MENU_WIDTH);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(MENU_HEIGHT);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(frame.width);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(frame.height);
  const host = document.createElement("div");
  document.body.appendChild(host);
  vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockReturnValue(host);

  render(
    <TerminalContextMenu
      tabId="t1"
      x={x}
      y={y}
      canCopy
      onCopy={vi.fn()}
      onPaste={vi.fn()}
      onClose={vi.fn()}
    />,
    { container: document.body.appendChild(document.createElement("div")) },
  );
  return screen.getByTestId("terminal-context-menu-t1");
}

describe("TerminalContextMenu placement", () => {
  it("renders at the click point when there is room", () => {
    const menu = renderMenuInFrame(100, 100);
    expect(menu.style.left).toBe("100px");
    expect(menu.style.top).toBe("100px");
  });

  it("flips upward near the bottom edge so the items stay clickable", () => {
    // The reported bug, at the DOM level.
    const menu = renderMenuInFrame(100, 380);
    expect(menu.style.top).toBe(`${380 - MENU_HEIGHT}px`);
    expect(Number.parseInt(menu.style.top, 10) + MENU_HEIGHT).toBeLessThanOrEqual(400);
  });

  it("flips leftward near the right edge", () => {
    const menu = renderMenuInFrame(780, 100);
    expect(menu.style.left).toBe(`${780 - MENU_WIDTH}px`);
  });

  it("flips both axes in the bottom-right corner", () => {
    const menu = renderMenuInFrame(795, 395);
    expect(menu.style.left).toBe(`${795 - MENU_WIDTH}px`);
    expect(menu.style.top).toBe(`${395 - MENU_HEIGHT}px`);
  });

  it("still closes on Escape after being repositioned", () => {
    // Guard against the placement effect interfering with dismissal.
    const onClose = vi.fn();
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(MENU_WIDTH);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(MENU_HEIGHT);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
    render(
      <TerminalContextMenu
        tabId="t1"
        x={795}
        y={395}
        canCopy
        onCopy={vi.fn()}
        onPaste={vi.fn()}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalled();
  });
});
