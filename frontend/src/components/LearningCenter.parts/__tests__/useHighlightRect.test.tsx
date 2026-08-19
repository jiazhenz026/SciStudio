/**
 * ADR-053 Learning Center (#2057) — following the element a step points at.
 *
 * The cases here are the ones that decide whether the highlight is usable:
 * a target that is not on screen yet (normal — a step routes to a tab and then
 * points inside it), a target that is in the DOM but not laid out (a collapsed
 * panel), and a target that moves without any scroll or resize event to listen
 * for (a canvas node under a pan). All three resolve to a number set the caller
 * can act on, or to `null` meaning "there is nothing to point at".
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHighlightRect, type HighlightRect } from "../useHighlightRect";

function Probe({ target, args }: { target: string | null; args?: Record<string, string> }) {
  const rect = useHighlightRect(target === null ? null : { target, args: args ?? {} });
  return (
    <output data-testid="rect">
      {rect === null ? "none" : `${rect.left},${rect.top},${rect.width},${rect.height}`}
    </output>
  );
}

/** Give an element a laid-out box; jsdom reports zeroes for everything. */
function box(element: HTMLElement, rect: HighlightRect): void {
  element.getBoundingClientRect = () =>
    ({
      ...rect,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
    }) as DOMRect;
}

function anchor(target: string, key?: string): HTMLElement {
  const element = document.createElement("div");
  element.setAttribute("data-tutorial-target", target);
  if (key !== undefined) element.setAttribute("data-tutorial-target-key", key);
  document.body.append(element);
  return element;
}

beforeEach(() => {
  // The hook drives itself off requestAnimationFrame; timers keep the loop
  // running under the test's control rather than at the display's pace.
  vi.stubGlobal(
    "requestAnimationFrame",
    (callback: FrameRequestCallback) =>
      setTimeout(() => callback(performance.now()), 0) as unknown as number,
  );
  vi.stubGlobal("cancelAnimationFrame", (handle: number) => clearTimeout(handle));
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("useHighlightRect", () => {
  it("reports nothing for a step that points at nothing", async () => {
    render(<Probe target={null} />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("none"));
  });

  it("reports nothing while the target has not rendered yet", async () => {
    /*
     * The normal case at step entry: the step routes to a tab and points at
     * something inside it, and the route's render has not landed. The card
     * falls back to the center rather than cutting a hole out of nothing.
     */
    render(<Probe target="plots_new_button" />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("none"));
  });

  it("finds the target once it appears", async () => {
    render(<Probe target="run_button" />);
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("none"));

    box(anchor("run_button"), { top: 12, left: 34, width: 56, height: 78 });

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("34,12,56,78"));
  });

  it("follows the target when it moves with no scroll or resize event", async () => {
    /*
     * A canvas node under a React Flow pan: the element's own box changes
     * because an ancestor's transform changed, which fires no event any
     * observer could subscribe to. This is why the hook runs a frame loop.
     */
    const element = anchor("node", "load_data");
    box(element, { top: 100, left: 100, width: 80, height: 80 });
    render(<Probe args={{ block_type: "load_data" }} target="node" />);
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("100,100,80,80"));

    box(element, { top: 140, left: 260, width: 80, height: 80 });

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("260,140,80,80"));
  });

  it("treats a target laid out to nothing as absent", async () => {
    // In the DOM, zero-sized: a collapsed panel, or a tab mounted but hidden.
    box(anchor("data_preview"), { top: 0, left: 0, width: 0, height: 0 });

    render(<Probe target="data_preview" />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("none"));
  });

  it("distinguishes one entity from its siblings", async () => {
    box(anchor("palette_block", "load_data"), { top: 10, left: 10, width: 70, height: 70 });
    box(anchor("palette_block", "save_data"), { top: 90, left: 10, width: 70, height: 70 });

    render(<Probe args={{ block_type: "save_data" }} target="palette_block" />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("10,90,70,70"));
  });

  it("goes back to nothing when the target disappears", async () => {
    // Leaving the tab the target lived in, mid-step.
    const element = anchor("history_restore_button");
    box(element, { top: 5, left: 5, width: 40, height: 20 });
    render(<Probe target="history_restore_button" />);
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("5,5,40,20"));

    element.remove();

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("none"));
  });
  /*
   * A control that opens a menu is measured together with what it opened.
   *
   * The defect: the step card is placed beside the target, the target was only
   * the New button, and the menu the step tells the reader to choose from opens
   * into the space beside it — so the card landed on top of the entries. The
   * pair is what the reader is acting on while the menu is open.
   */
  it("grows to include the menu its target has opened", async () => {
    const trigger = anchor("new_menu_button");
    box(trigger, { top: 10, left: 20, width: 60, height: 30 });
    const menu = document.createElement("div");
    menu.id = "menu-1";
    box(menu, { top: 40, left: 20, width: 220, height: 180 });
    document.body.append(menu);
    trigger.setAttribute("aria-controls", "menu-1");
    render(<Probe target="new_menu_button" />);
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,60,30"));

    trigger.setAttribute("aria-expanded", "true");

    // The union of button and menu: from the button's top-left to the menu's
    // bottom-right.
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,220,210"));
  });

  it("shrinks back to the control when the menu closes", async () => {
    const trigger = anchor("new_menu_button");
    box(trigger, { top: 10, left: 20, width: 60, height: 30 });
    const menu = document.createElement("div");
    menu.id = "menu-2";
    box(menu, { top: 40, left: 20, width: 220, height: 180 });
    document.body.append(menu);
    trigger.setAttribute("aria-controls", "menu-2");
    trigger.setAttribute("aria-expanded", "true");
    render(<Probe target="new_menu_button" />);
    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,220,210"));

    trigger.setAttribute("aria-expanded", "false");

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,60,30"));
  });

  it("ignores a panel a collapsed control still names", async () => {
    // `aria-controls` survives the menu closing; `aria-expanded` is the fact.
    const trigger = anchor("new_menu_button");
    box(trigger, { top: 10, left: 20, width: 60, height: 30 });
    const menu = document.createElement("div");
    menu.id = "menu-3";
    box(menu, { top: 40, left: 20, width: 220, height: 180 });
    document.body.append(menu);
    trigger.setAttribute("aria-controls", "menu-3");

    render(<Probe target="new_menu_button" />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,60,30"));
  });

  it("keeps the control's own box when the panel it names is gone", async () => {
    const trigger = anchor("new_menu_button");
    box(trigger, { top: 10, left: 20, width: 60, height: 30 });
    trigger.setAttribute("aria-expanded", "true");
    trigger.setAttribute("aria-controls", "never-rendered");

    render(<Probe target="new_menu_button" />);

    await waitFor(() => expect(screen.getByTestId("rect")).toHaveTextContent("20,10,60,30"));
  });
});
