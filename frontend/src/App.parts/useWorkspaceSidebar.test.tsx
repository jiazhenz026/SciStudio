import { act, renderHook } from "@testing-library/react";
import type { PanelImperativeHandle, PanelSize } from "react-resizable-panels";
import { describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { useWorkspaceSidebar } from "./useWorkspaceSidebar";

function sidebar() {
  let collapsed = true;
  let onResize = (_size: PanelSize) => {};
  const panel = {
    collapse: vi.fn(() => {
      collapsed = true;
    }),
    expand: vi.fn(() => {
      collapsed = false;
      onResize({ asPercentage: 10, inPixels: 126 });
    }),
    isCollapsed: () => collapsed,
    getSize: () => ({ asPercentage: 0, inPixels: 0 }),
    resize: vi.fn(),
  } satisfies PanelImperativeHandle;
  const ref = { current: panel };
  const hook = renderHook(({ closed, ai }) => useWorkspaceSidebar(ref, closed, ai), {
    initialProps: { closed: true, ai: false },
  });
  onResize = (size) => hook.result.current(size);
  return { panel, ...hook };
}

describe("workspace sidebar expansion", () => {
  it("opens a initially collapsed desktop sidebar at 280px, not minSize", () => {
    const { panel, rerender } = sidebar();
    rerender({ closed: false, ai: false });
    expect(panel.resize).toHaveBeenLastCalledWith("280px");
  });

  it("preserves manual desktop width through drag-collapse and reopen", () => {
    const { panel, result, rerender } = sidebar();
    rerender({ closed: false, ai: false });
    act(() => result.current({ asPercentage: 24, inPixels: 310 }));
    act(() => result.current({ asPercentage: 0, inPixels: 0 }));
    expect(useAppStore.getState().paletteCollapsed).toBe(true);
    rerender({ closed: true, ai: false });
    rerender({ closed: false, ai: false });
    expect(panel.resize).toHaveBeenLastCalledWith("310px");
  });

  it("keeps AI and desktop preferred widths separate", () => {
    const { panel, result, rerender } = sidebar();
    rerender({ closed: false, ai: false });
    act(() => result.current({ asPercentage: 24, inPixels: 310 }));
    rerender({ closed: false, ai: true });
    expect(panel.resize).toHaveBeenLastCalledWith("28%");
    act(() => result.current({ asPercentage: 35, inPixels: 210 }));
    rerender({ closed: false, ai: false });
    expect(panel.resize).toHaveBeenLastCalledWith("310px");
  });
});
