// #1841 / #1847 — regression guard for the interactive-panel reskin: the
// DataRouter / PairEditor modals must adopt the shared design system (the
// `ui/Button` primitive + brand tokens) instead of the old hand-rolled cold
// `bg-blue-500` action buttons + `border-stone-*` chrome.

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, within } from "@testing-library/react";

afterEach(cleanup);

import { DataRouterModal } from "./DataRouterModal";
import { PairEditorModal } from "./PairEditorModal";

describe("interactive modals adopt the shared design system (#1841)", () => {
  it("DataRouterModal renders Confirm/Cancel as shared ui/Button (brand, not cold blue)", () => {
    const { container } = render(
      <DataRouterModal
        blockId="blk-1"
        inputPorts={["in_1"]}
        outputPorts={["out_1"]}
        // No items → everything is trivially assigned, so Confirm is enabled.
        itemsPerPort={{ in_1: [] }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const confirm = within(container).getByRole("button", { name: "Confirm" });
    const cancel = within(container).getByRole("button", { name: "Cancel" });

    // Shared Button primitive: default variant => brand primary; outline => input border.
    expect(confirm.className).toContain("bg-primary");
    expect(cancel.className).toContain("border-input");

    // The old cold action-button blue must be gone (categorical bg-blue-50
    // pairing tints are unaffected — we only guard the 500/600 action shade).
    expect(container.innerHTML).not.toMatch(/bg-blue-(500|600)/);
    // Chrome migrated off the generic stone neutrals onto the ink brand token.
    expect(container.innerHTML).not.toMatch(/border-stone-\d/);
  });

  it("PairEditorModal renders Confirm/Cancel as shared ui/Button (brand, not cold blue)", () => {
    const { container } = render(
      <PairEditorModal
        blockId="blk-2"
        ports={["a", "b"]}
        itemsPerPort={{
          a: [{ index: 0, name: "x", type: "Array" }],
          b: [{ index: 0, name: "y", type: "Array" }],
        }}
        collectionLength={1}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const confirm = within(container).getByRole("button", { name: "Confirm" });
    const cancel = within(container).getByRole("button", { name: "Cancel" });

    expect(confirm.className).toContain("bg-primary");
    expect(cancel.className).toContain("border-input");
    expect(container.innerHTML).not.toMatch(/bg-blue-(500|600)/);
    expect(container.innerHTML).not.toMatch(/border-stone-\d/);
  });
});
