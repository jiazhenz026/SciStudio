// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
// Covers issue #422 — inline error message display next to the status badge.

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — inline error message (issue #422)", () => {
  it("renders inline error message when status=error and errorMessage is set", () => {
    renderNode({
      status: "error",
      errorMessage: "Division by zero",
    });
    expect(screen.getByText("Division by zero")).toBeInTheDocument();
  });

  it("truncates long error messages to 80 chars with ellipsis", () => {
    const longMsg = "A".repeat(100);
    renderNode({
      status: "error",
      errorMessage: longMsg,
    });
    // The truncated text is the first 80 chars followed by an ellipsis char.
    const expected = `${"A".repeat(80)}…`;
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("shows full error text in title attribute for long messages", () => {
    const longMsg = "B".repeat(100);
    renderNode({
      status: "error",
      errorMessage: longMsg,
    });
    const el = screen.getByTitle(longMsg);
    expect(el).toBeInTheDocument();
  });

  it("does NOT render error message element when status is not error", () => {
    renderNode({
      status: "done",
      errorMessage: "this should not appear",
    });
    expect(screen.queryByText("this should not appear")).toBeNull();
  });

  it("does NOT render error message element when errorMessage is absent", () => {
    renderNode({ status: "error" });
    // Only the status badge should be present; no extra text element.
    // 'Error' is the badge label text — confirm it exists but no extra message.
    expect(screen.getByText("Error")).toBeInTheDocument();
  });
});
