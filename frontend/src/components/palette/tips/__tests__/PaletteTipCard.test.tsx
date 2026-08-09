// #1997 — the overlay itself: it has to be readable when it is up, harmless
// when it is down, and gone for good once the user has said no twice.

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PaletteTipCard } from "../PaletteTipCard";
import { resolveTip } from "../tipPool";
import { TIP_HIDDEN_MS, TIP_SNOOZE_MS } from "../useTipRotation";

beforeEach(() => {
  vi.useFakeTimers();
  // A fixed rotation start keeps the rendered tip deterministic.
  vi.spyOn(Math, "random").mockReturnValue(0);
});

afterEach(() => {
  // The suite is not run with globals, so unmounting is on us; several cases
  // render more than once and would otherwise query across leftovers.
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  // `forceOverflow` patches the prototype; leaving it in place would follow
  // the suite into the next file's jsdom.
  for (const prop of ["scrollHeight", "clientHeight"]) {
    delete (HTMLParagraphElement.prototype as unknown as Record<string, unknown>)[prop];
    delete (HTMLSpanElement.prototype as unknown as Record<string, unknown>)[prop];
  }
});

const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

/** Install a ResizeObserver that fires its callback as soon as it observes. */
function installResizeObserver() {
  class ImmediateResizeObserver {
    constructor(private readonly cb: ResizeObserverCallback) {}
    observe() {
      this.cb([], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ImmediateResizeObserver);
}

/** Make the body element report itself as overflowing its clamped box. */
function forceOverflow(overflowing: boolean) {
  patchOverflow(HTMLParagraphElement, overflowing);
}

/** Same, for the title — it is a `span` inside the title paragraph. */
function forceTitleOverflow(overflowing: boolean) {
  patchOverflow(HTMLSpanElement, overflowing);
}

function patchOverflow(ctor: { prototype: object }, overflowing: boolean) {
  Object.defineProperty(ctor.prototype, "scrollHeight", {
    configurable: true,
    get: () => (overflowing ? 60 : 20),
  });
  Object.defineProperty(ctor.prototype, "clientHeight", {
    configurable: true,
    get: () => 20,
  });
}

describe("PaletteTipCard", () => {
  it("shows a tip once the first quiet gap has passed", () => {
    render(<PaletteTipCard />);

    const card = screen.getByTestId("palette-tip");
    expect(card).toHaveClass("opacity-0");
    // While down it must not swallow clicks aimed at the tiles underneath.
    expect(card).toHaveClass("pointer-events-none");

    advance(TIP_HIDDEN_MS);
    const shown = screen.getByTestId("palette-tip");
    expect(shown).toHaveClass("opacity-100");
    expect(shown).not.toHaveClass("pointer-events-none");
    expect(screen.getByText(resolveTip(1)!.title)).toBeInTheDocument();
  });

  it("takes the card down on dismiss and brings it back after the snooze", () => {
    render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);

    fireEvent.click(screen.getByLabelText("Dismiss tip"));
    expect(screen.getByTestId("palette-tip")).toHaveClass("opacity-0");

    advance(TIP_SNOOZE_MS);
    expect(screen.getByTestId("palette-tip")).toHaveClass("opacity-100");
  });

  it("stops rendering entirely after a second dismissal", () => {
    render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);

    fireEvent.click(screen.getByLabelText("Dismiss tip"));
    advance(TIP_SNOOZE_MS);
    fireEvent.click(screen.getByLabelText("Dismiss tip"));

    expect(screen.queryByTestId("palette-tip")).not.toBeInTheDocument();
  });

  it("offers an expand control only when the body does not fit", () => {
    installResizeObserver();
    forceOverflow(false);

    const { unmount } = render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
    unmount();

    forceOverflow(true);
    render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("drops the two-line clamp while expanded", () => {
    installResizeObserver();
    forceOverflow(true);

    render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);

    const body = screen.getByText(resolveTip(1)!.body);
    expect(body).toHaveClass("line-clamp-2");

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(body).not.toHaveClass("line-clamp-2");

    fireEvent.click(screen.getByRole("button", { name: "Less" }));
    expect(body).toHaveClass("line-clamp-2");
  });

  it("wraps a long title to two lines and releases it when expanded", () => {
    installResizeObserver();
    forceOverflow(false);
    // Only the title overflows: the expand control still has to appear, and it
    // has to free the title as well as the body (owner directive, #1997).
    forceTitleOverflow(true);

    render(<PaletteTipCard />);
    advance(TIP_HIDDEN_MS);

    const title = screen.getByText(resolveTip(1)!.title);
    expect(title).toHaveClass("line-clamp-2");

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(title).not.toHaveClass("line-clamp-2");
  });
});
