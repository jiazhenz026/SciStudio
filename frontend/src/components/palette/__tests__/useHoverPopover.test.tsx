// The shared hover state machine behind the interactive popover (ADR-053
// FR-044). The behaviour under test is exactly the one the old tile-driven
// implementation could not provide: surviving the POPOVER_GAP between tile and
// card so a button inside the card can be reached at all.

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  computeTileAnchor,
  POPOVER_CLOSE_DELAY_MS,
  POPOVER_GAP,
  POPOVER_MAX_HEIGHT,
  POPOVER_OPEN_DELAY_MS,
  useHoverPopover,
} from "../hoverPopover";

const rect = (right: number, top: number) => ({ right, top });

describe("computeTileAnchor", () => {
  it("opens to the right of the tile across the configured gap", () => {
    expect(computeTileAnchor(rect(120, 40), 1000)).toEqual({ left: 120 + POPOVER_GAP, top: 40 });
  });

  it("clamps the top so a tile near the bottom edge still yields a visible card", () => {
    const viewportHeight = 500;
    expect(computeTileAnchor(rect(120, 480), viewportHeight).top).toBe(
      viewportHeight - POPOVER_MAX_HEIGHT,
    );
  });

  it("never clamps above the gap on a viewport shorter than the card", () => {
    // A 100px viewport cannot fit the 240px card, so the clamp floors at the
    // gap rather than going negative and pushing the card off the top edge.
    expect(computeTileAnchor(rect(120, 10), 100).top).toBe(POPOVER_GAP);
    expect(computeTileAnchor(rect(120, 90), 100).top).toBe(POPOVER_GAP);
  });
});

describe("useHoverPopover", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("opens only after the dwell delay", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS - 1);
    });
    expect(result.current.hovered).toBeNull();

    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(result.current.hovered?.item).toBe("Cellpose");
    expect(result.current.hovered?.anchor.left).toBe(100 + POPOVER_GAP);
  });

  it("does not open when the pointer leaves before the dwell elapses", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => result.current.scheduleClose());
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS + POPOVER_CLOSE_DELAY_MS + 10);
    });
    expect(result.current.hovered).toBeNull();
  });

  it("stays open across the tile→popover gap when the card is reached in time", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });

    // Pointer leaves the tile into the dead space of POPOVER_GAP...
    act(() => result.current.scheduleClose());
    act(() => {
      vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS - 1);
    });
    expect(result.current.hovered?.item).toBe("Cellpose");

    // ...and reaches the card, which cancels the pending close.
    act(() => result.current.keepOpen());
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current.hovered?.item).toBe("Cellpose");
  });

  it("closes once the grace period elapses with the pointer nowhere", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });
    act(() => result.current.scheduleClose());
    act(() => {
      vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS);
    });
    expect(result.current.hovered).toBeNull();
  });

  it("closeNow drops the card immediately and cancels a pending open", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });
    act(() => result.current.closeNow());
    expect(result.current.hovered).toBeNull();

    act(() => result.current.openFor("Annotate", rect(100, 20)));
    act(() => result.current.closeNow());
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current.hovered).toBeNull();
  });

  it("re-targets to the newest tile and cancels the previous tile's close", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });
    act(() => result.current.scheduleClose());
    act(() => result.current.openFor("Annotate", rect(200, 60)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });
    expect(result.current.hovered?.item).toBe("Annotate");
    expect(result.current.hovered?.anchor.left).toBe(200 + POPOVER_GAP);
  });

  it("exposes popover props that both mark the card interactive and keep it open", () => {
    const { result } = renderHook(() => useHoverPopover<string>());
    expect(result.current.popoverProps.interactive).toBe(true);

    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    act(() => {
      vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS);
    });
    act(() => result.current.scheduleClose());
    act(() => result.current.popoverProps.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current.hovered?.item).toBe("Cellpose");

    act(() => result.current.popoverProps.onMouseLeave());
    act(() => {
      vi.advanceTimersByTime(POPOVER_CLOSE_DELAY_MS);
    });
    expect(result.current.hovered).toBeNull();
  });

  it("leaves no timer behind after unmount", () => {
    const { result, unmount } = renderHook(() => useHoverPopover<string>());
    act(() => result.current.openFor("Cellpose", rect(100, 20)));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
