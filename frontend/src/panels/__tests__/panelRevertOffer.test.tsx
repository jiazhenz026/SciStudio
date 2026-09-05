// ADR-054 FR-028 — "the host MUST report the failure explicitly and offer to
// revert".
//
// The audit found the reporting half shipped and the offering half missing:
// `grep -rni revert frontend/src` returned four hits and none of them was about
// a panel. These tests pin the control itself; the decision about *when* it is
// offered is `store/__tests__/panelRevertOffer.test.ts`.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PanelErrorSurface } from "../PanelErrorSurface";
import type { PanelFailure } from "../panelFrame";

const FAILURE: PanelFailure = {
  panelId: "core.plot.basic",
  reason: "load_timeout",
  message: "the document did not load within 8000 ms",
};

afterEach(cleanup);

describe("PanelErrorSurface", () => {
  it("offers to revert when the failed panel is an edited copy", () => {
    const onRevert = vi.fn();
    render(<PanelErrorSurface failure={FAILURE} revert={{ restoresTier: "core", onRevert }} />);

    const button = screen.getByTestId("panel-error-revert");
    expect(button).toHaveTextContent("Revert to the core panel");
    fireEvent.click(button);
    expect(onRevert).toHaveBeenCalledTimes(1);
  });

  it("still reports the failure explicitly beside the offer (FR-014)", () => {
    render(
      <PanelErrorSurface failure={FAILURE} revert={{ restoresTier: "core", onRevert: vi.fn() }} />,
    );

    const surface = screen.getByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-id", "core.plot.basic");
    expect(surface).toHaveTextContent("load_timeout");
    expect(surface).toHaveTextContent("the document did not load within 8000 ms");
  });

  it("offers nothing when the panel shadows nothing", () => {
    // Not a disabled button: there is no original behind this panel, and
    // deleting the only copy of one is a different request nobody made.
    render(<PanelErrorSurface failure={FAILURE} />);
    expect(screen.queryByTestId("panel-error-revert")).toBeNull();
  });

  it("disables the control while the revert is in flight", () => {
    render(
      <PanelErrorSurface
        failure={FAILURE}
        revert={{ restoresTier: "user", onRevert: vi.fn(), pending: true }}
      />,
    );
    expect(screen.getByTestId("panel-error-revert")).toBeDisabled();
  });

  it("shows a refusal from the revert route rather than swallowing it", () => {
    render(
      <PanelErrorSurface
        failure={FAILURE}
        revert={{
          restoresTier: "core",
          onRevert: vi.fn(),
          error: "panel 'core.plot.basic' shadows nothing",
        }}
      />,
    );
    expect(screen.getByTestId("panel-error-revert-error")).toHaveTextContent("shadows nothing");
  });
});
