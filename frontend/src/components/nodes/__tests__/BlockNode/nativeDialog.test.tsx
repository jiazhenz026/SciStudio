// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
// Covers issue #678 — native-dialog status-aware fallback behavior:
//   - HTTP 500 → fall back to the in-app FileBrowserModal,
//   - HTTP 504 → surface a console.error rather than falling back,
//   - non-ApiError network failure → fall back defensively.

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeSchema, openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode - native dialog status-aware fallback (#678)", () => {
  // A non-io block with a file_browser config field renders a Browse "..." button.
  function renderBrowseField() {
    return renderNode({
      category: "process",
      blockType: "test_block",
      schema: makeSchema({
        base_category: "process",
        type_name: "test_block",
        config_schema: {
          type: "object",
          properties: {
            path: { type: "string", ui_widget: "file_browser", ui_priority: 0 },
          },
        },
      }),
    });
  }

  function findBrowseButton(): HTMLElement {
    const btn = screen.getByTitle("Browse filesystem");
    expect(btn).toBeInTheDocument();
    return btn;
  }

  function getFileBrowserHeading(): HTMLElement | null {
    return screen.queryByText("Select File");
  }

  it("falls back to in-app FileBrowserModal when native dialog returns HTTP 500", async () => {
    const { ApiError } = await import("../../../../lib/api");
    openNativeDialogMock.mockRejectedValueOnce(
      new ApiError("Native dialog command not available on this platform (Linux)", 500),
    );

    renderBrowseField();
    expect(getFileBrowserHeading()).toBeNull();
    await userEvent.click(findBrowseButton());

    // Modal opens (heading "Select File" is the modal's title).
    expect(getFileBrowserHeading()).toBeInTheDocument();
  });

  it("does NOT open in-app FileBrowserModal when native dialog returns HTTP 504", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const { ApiError } = await import("../../../../lib/api");
    openNativeDialogMock.mockRejectedValueOnce(new ApiError("Dialog timed out", 504));

    renderBrowseField();
    await userEvent.click(findBrowseButton());

    // Modal must NOT open on a 504 - that is the deprecated picker we
    // are explicitly avoiding (#678).
    expect(getFileBrowserHeading()).toBeNull();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("falls back to in-app FileBrowserModal on a non-ApiError network failure", async () => {
    openNativeDialogMock.mockRejectedValueOnce(new Error("network down"));

    renderBrowseField();
    await userEvent.click(findBrowseButton());

    expect(getFileBrowserHeading()).toBeInTheDocument();
  });
});
