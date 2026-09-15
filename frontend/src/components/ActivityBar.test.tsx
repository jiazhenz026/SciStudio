// #2090 — the VS Code-style activity bar: icon rail, hover tooltips, and the
// active-section marker (hidden while the panel is collapsed).

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACTIVITY_BAR_ORDER_STORAGE_KEY } from "../lib/activityBarOrder";

import { ActivityBar, type ActivityBarProps } from "./ActivityBar";
import { TooltipProvider } from "./ui/tooltip";

const DEFAULT_KEYS = ["blocks", "workflows", "miniapps", "types", "data", "project"];
// Each rail slot is 44px tall (40px button + 4px gap) starting at y=0.
const SLOT = 44;

// jsdom has no PointerEvent, so `fireEvent.pointer*` would drop `pointerId`
// and `clientY`. A MouseEvent subclass carrying `pointerId` is all the rail
// reads.
if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  }
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

function railKeys(): string[] {
  return [...screen.getByTestId("activity-bar").querySelectorAll("button[data-testid]")]
    .map((button) => button.getAttribute("data-testid")!.replace("activity-bar-", ""))
    .filter((key) => key !== "reset-order");
}

function savedOrder(): unknown {
  const raw = window.localStorage.getItem(ACTIVITY_BAR_ORDER_STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
}

/** Give every rail button a rect from its current DOM position. */
function mockSlotRects() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const rail = screen.getByTestId("activity-bar");
    const index = [...rail.querySelectorAll("button[data-testid^='activity-bar-']")].indexOf(this);
    const top = Math.max(index, 0) * SLOT;
    return {
      top,
      bottom: top + 40,
      height: 40,
      left: 0,
      right: 40,
      width: 40,
      x: 0,
      y: top,
      toJSON: () => ({}),
    } as DOMRect;
  });
}

function drag(label: string, fromY: number, toY: number) {
  const button = screen.getByRole("button", { name: label });
  fireEvent.pointerDown(button, { button: 0, pointerId: 1, clientY: fromY });
  fireEvent.pointerMove(button, { pointerId: 1, clientY: fromY + (toY > fromY ? 10 : -10) });
  fireEvent.pointerMove(button, { pointerId: 1, clientY: toY });
  fireEvent.pointerUp(button, { pointerId: 1, clientY: toY });
  // The browser follows a pointerup on the pressed element with a click.
  fireEvent.click(button, { detail: 1 });
}

function renderBar(overrides: Partial<ActivityBarProps> = {}) {
  const onSelect = vi.fn();
  render(
    <TooltipProvider delayDuration={0}>
      <ActivityBar activeTab="blocks" panelOpen onSelect={onSelect} {...overrides} />
    </TooltipProvider>,
  );
  return onSelect;
}

describe("ActivityBar", () => {
  it("renders one icon button per left-panel section", () => {
    renderBar();
    expect(screen.getByTestId("activity-bar")).toBeInTheDocument();
    // ADR-054 FR-031 — `MiniApps` took the `Previewers` slot; the previewer
    // list moved into the preview column behind All Previewers (FR-033).
    for (const label of ["Blocks", "Data types", "Workflows", "Data", "MiniApps", "Project"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("orders the sections Blocks, Workflows, MiniApps, Data types, Data, Project by default (#2415)", () => {
    renderBar();
    expect(railKeys()).toEqual(DEFAULT_KEYS);
  });

  it("reports the clicked section", () => {
    const onSelect = renderBar();
    fireEvent.click(screen.getByRole("button", { name: "Workflows" }));
    expect(onSelect).toHaveBeenCalledWith("workflows");
    fireEvent.click(screen.getByRole("button", { name: "Project" }));
    expect(onSelect).toHaveBeenCalledWith("project");
  });

  it("marks the active section only while the panel is open", () => {
    renderBar({ activeTab: "types", panelOpen: true });
    expect(screen.getByRole("button", { name: "Data types" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Blocks" })).toHaveAttribute("aria-pressed", "false");

    cleanup();
    renderBar({ activeTab: "types", panelOpen: false });
    // VS Code behavior: a collapsed panel shows no active marker at all.
    expect(screen.getByRole("button", { name: "Data types" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("shows the section name in a tooltip on hover/focus", async () => {
    renderBar();
    fireEvent.focus(screen.getByRole("button", { name: "Workflows" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Workflows");
  });

  describe("reordering (#2415)", () => {
    it("dragging an icon moves it, persists the order, and does not select", () => {
      mockSlotRects();
      const onSelect = renderBar();
      // Project (slot 5, centre y=222) dragged to Blocks' slot (centre y=20).
      drag("Project", 5 * SLOT + 20, 20);
      expect(railKeys()).toEqual(["project", "blocks", "workflows", "miniapps", "types", "data"]);
      expect(savedOrder()).toEqual(railKeys());
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("keeps the dragged order across a remount (per-viewer preference)", () => {
      mockSlotRects();
      renderBar();
      drag("Blocks", 20, 2 * SLOT + 20);
      const after = railKeys();
      expect(after).toEqual(["workflows", "miniapps", "blocks", "types", "data", "project"]);
      cleanup();
      renderBar();
      expect(railKeys()).toEqual(after);
    });

    it("a press that stays under the drag threshold is still a click", () => {
      mockSlotRects();
      const onSelect = renderBar();
      const button = screen.getByRole("button", { name: "Data" });
      fireEvent.pointerDown(button, { button: 0, pointerId: 1, clientY: 4 * SLOT + 20 });
      fireEvent.pointerMove(button, { pointerId: 1, clientY: 4 * SLOT + 22 });
      fireEvent.pointerUp(button, { pointerId: 1, clientY: 4 * SLOT + 22 });
      fireEvent.click(button, { detail: 1 });
      expect(onSelect).toHaveBeenCalledWith("data");
      expect(railKeys()).toEqual(DEFAULT_KEYS);
      expect(savedOrder()).toBeNull();
    });

    it("the click right after a drag is swallowed, the next one selects", () => {
      mockSlotRects();
      const onSelect = renderBar();
      drag("Workflows", SLOT + 20, 3 * SLOT + 20);
      expect(onSelect).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Workflows" }), { detail: 1 });
      expect(onSelect).toHaveBeenCalledWith("workflows");
    });

    it("Alt+ArrowUp / Alt+ArrowDown move the focused icon and keep focus on it", () => {
      renderBar();
      const miniapps = screen.getByRole("button", { name: "MiniApps" });
      miniapps.focus();
      fireEvent.keyDown(miniapps, { key: "ArrowUp", altKey: true });
      expect(railKeys()).toEqual(["blocks", "miniapps", "workflows", "types", "data", "project"]);
      expect(screen.getByRole("button", { name: "MiniApps" })).toHaveFocus();
      fireEvent.keyDown(screen.getByRole("button", { name: "MiniApps" }), {
        key: "ArrowDown",
        altKey: true,
      });
      fireEvent.keyDown(screen.getByRole("button", { name: "MiniApps" }), {
        key: "ArrowDown",
        altKey: true,
      });
      expect(railKeys()).toEqual(["blocks", "workflows", "types", "miniapps", "data", "project"]);
      expect(savedOrder()).toEqual(railKeys());
      // Plain arrows and moves past either end change nothing.
      fireEvent.keyDown(screen.getByRole("button", { name: "Blocks" }), { key: "ArrowDown" });
      fireEvent.keyDown(screen.getByRole("button", { name: "Blocks" }), {
        key: "ArrowUp",
        altKey: true,
      });
      expect(railKeys()).toEqual(["blocks", "workflows", "types", "miniapps", "data", "project"]);
    });

    it("merges a saved order: unknown keys dropped, missing entries at their default position", () => {
      window.localStorage.setItem(
        ACTIVITY_BAR_ORDER_STORAGE_KEY,
        JSON.stringify(["project", "retired", "data", "blocks", "project"]),
      );
      renderBar();
      // workflows/miniapps follow blocks; types has no kept predecessor after
      // them, so it lands after miniapps too.
      expect(railKeys()).toEqual(["project", "data", "blocks", "workflows", "miniapps", "types"]);
    });

    it("ignores a corrupt saved value", () => {
      window.localStorage.setItem(ACTIVITY_BAR_ORDER_STORAGE_KEY, "{not json");
      renderBar();
      expect(railKeys()).toEqual(DEFAULT_KEYS);
    });

    it("Reset order in the rail's context menu restores the default", () => {
      window.localStorage.setItem(
        ACTIVITY_BAR_ORDER_STORAGE_KEY,
        JSON.stringify(["project", "data", "types", "miniapps", "workflows", "blocks"]),
      );
      renderBar();
      fireEvent.contextMenu(screen.getByTestId("activity-bar"), { clientX: 10, clientY: 10 });
      fireEvent.click(screen.getByRole("menuitem", { name: "Reset order" }));
      expect(railKeys()).toEqual(DEFAULT_KEYS);
      expect(savedOrder()).toBeNull();
      expect(screen.queryByTestId("activity-bar-menu")).not.toBeInTheDocument();
    });

    it("disables Reset order when the rail already has the default order", () => {
      renderBar();
      fireEvent.contextMenu(screen.getByTestId("activity-bar"), { clientX: 10, clientY: 10 });
      expect(screen.getByRole("menuitem", { name: "Reset order" })).toBeDisabled();
      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.queryByTestId("activity-bar-menu")).not.toBeInTheDocument();
    });

    it("keeps the AI presentation's Preview entry last and not reorderable", () => {
      window.history.replaceState(null, "", "/?ui=ai");
      window.localStorage.setItem(
        ACTIVITY_BAR_ORDER_STORAGE_KEY,
        JSON.stringify(["project", "preview", "blocks"]),
      );
      renderBar();
      expect(railKeys()[railKeys().length - 1]).toBe("preview");
      expect(railKeys().filter((key) => key === "preview")).toHaveLength(1);
      const preview = screen.getByRole("button", { name: "Preview" });
      act(() => preview.focus());
      fireEvent.keyDown(preview, { key: "ArrowUp", altKey: true });
      expect(railKeys()[railKeys().length - 1]).toBe("preview");
    });
  });
});
