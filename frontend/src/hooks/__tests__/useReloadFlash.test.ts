import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useReloadFlash } from "../useReloadFlash";

function attachElement(ref: { current: HTMLDivElement | null }) {
  const el = document.createElement("div");
  const animate = vi.fn();
  (el as unknown as { animate: typeof animate }).animate = animate;
  ref.current = el;
  return animate;
}

describe("useReloadFlash", () => {
  it("blinks only after trigger() and a subsequent data change", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReloadFlash<HTMLDivElement, number>(data),
      { initialProps: { data: 0 } },
    );
    const animate = attachElement(result.current.ref);

    // Data change without a trigger does not blink.
    rerender({ data: 1 });
    expect(animate).not.toHaveBeenCalled();

    // Trigger, then the next data change blinks once.
    result.current.trigger();
    rerender({ data: 2 });
    expect(animate).toHaveBeenCalledTimes(1);

    const [keyframes, options] = animate.mock.calls[0];
    expect(keyframes).toEqual([{ opacity: 1 }, { opacity: 0 }, { opacity: 1 }]);
    expect(options).toMatchObject({ duration: 100 });
  });

  it("does not blink on mount", () => {
    const { result } = renderHook(() => useReloadFlash<HTMLDivElement, number>(0));
    const animate = attachElement(result.current.ref);
    // No data change yet → no blink even though the element is attached.
    expect(animate).not.toHaveBeenCalled();
  });

  it("consumes the trigger so a later unrelated data change does not blink again", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReloadFlash<HTMLDivElement, number>(data),
      { initialProps: { data: 0 } },
    );
    const animate = attachElement(result.current.ref);

    result.current.trigger();
    rerender({ data: 1 });
    expect(animate).toHaveBeenCalledTimes(1);

    // A subsequent change with no new trigger must not blink.
    rerender({ data: 2 });
    expect(animate).toHaveBeenCalledTimes(1);
  });
});
