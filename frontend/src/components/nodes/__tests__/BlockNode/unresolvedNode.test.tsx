// #1988 — how the two ex-grey states actually render.
//
// The colour half of #1988 is covered by the palette tests; this file pins the
// half that colour cannot do: an unresolved node must keep LOOKING unresolved
// after the restyle, and it must say what is wrong in words a user can act on.

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { renderNode } from "./test-utils";

afterEach(cleanup);

function body(container: HTMLElement): HTMLElement {
  const el = container.querySelector("[data-testid='block-node-body']");
  if (!(el instanceof HTMLElement)) throw new Error("node body not rendered");
  return el;
}

describe("#1988 unresolved node rendering", () => {
  it("draws the body with a dashed outline", () => {
    const { container } = renderNode({ category: "unresolved", unresolved: true });
    expect(body(container).style.borderStyle).toBe("dashed");
  });

  it("leaves every resolved category solid", () => {
    const { container } = renderNode({ category: "process" });
    expect(body(container).style.borderStyle).toBe("");
  });

  it("stays dashed even when it borrows the IO palette", () => {
    // An unresolved loader is drawn with the IO body so it still reads as a
    // loader. If the dash were driven by the palette instead of by the fact,
    // that borrowed colour would be exactly the prettier styling #1988 says
    // must not hide the defect.
    const { container } = renderNode({
      category: "io",
      unresolved: true,
      uiIconHint: "folder-input",
    });
    const el = body(container);
    expect(el.style.borderStyle).toBe("dashed");
    expect(el.style.backgroundColor).toBe("rgb(159, 212, 238)");
  });

  it("leaves a no-category block solid — it works, it is just not one of the six", () => {
    const { container } = renderNode({ category: "unknown" });
    const el = body(container);
    expect(el.style.borderStyle).toBe("");
    expect(el.style.backgroundColor).toBe("rgb(181, 196, 242)");
  });

  it("does not fight the selection border", () => {
    // Selection repaints the border through `border-ember`; the dash would
    // otherwise override the selected affordance.
    const { container } = renderNode({ category: "unresolved", unresolved: true }, true);
    expect(body(container).style.borderStyle).toBe("");
  });

  it("raises the warning badge, not a silent node", () => {
    renderNode({ category: "unresolved", unresolved: true, problemSeverity: "warning" });
    const surface = screen.getByTestId("node-status-surface");
    expect(surface.getAttribute("data-surface-kind")).toBe("warning");
    expect(surface.getAttribute("data-icon")).toBe("alert-triangle");
  });

  it("names the missing block type instead of pointing at a Config that cannot help", () => {
    renderNode({
      category: "unresolved",
      unresolved: true,
      problemSeverity: "warning",
      blockType: "srs_baseline_block",
    });
    const title = screen.getByTestId("node-status-surface").getAttribute("title") ?? "";
    expect(title).toContain("srs_baseline_block");
    expect(title).toContain("not available in this project");
    expect(title).not.toContain("open Config");
  });

  it("offers no click-through on the unresolved warning", () => {
    // The shared warning handler opens BottomPanel Config, which cannot help a
    // block that never loaded — the tooltip says so, so the badge must not
    // still act as a control that goes there.
    renderNode({
      category: "unresolved",
      unresolved: true,
      problemSeverity: "warning",
      onWarningClick: () => {
        throw new Error("unresolved node must not route to Config");
      },
    });
    expect(screen.queryByTestId("node-status-surface-button")).toBeNull();
    expect(screen.getByTestId("node-status-surface")).toBeTruthy();
  });

  it("keeps the click-through for an ordinary warning", () => {
    renderNode({ category: "io", problemSeverity: "warning", onWarningClick: () => {} });
    expect(screen.getByTestId("node-status-surface-button")).toBeTruthy();
  });

  it("keeps the generic Config wording for the lossy-save warning", () => {
    // The unresolved copy is opt-in, so the pre-existing warning is unchanged.
    renderNode({ category: "io", problemSeverity: "warning" });
    const title = screen.getByTestId("node-status-surface").getAttribute("title") ?? "";
    expect(title).toBe("Warning — open Config for details");
  });

  it("shows the raw block type under an unresolved node so it can be identified", () => {
    renderNode({
      category: "unresolved",
      unresolved: true,
      label: "srs_baseline_block",
      blockType: "srs_baseline_block",
    });
    expect(screen.getByTestId("block-node-label").textContent).toBe("srs_baseline_block");
  });
});
