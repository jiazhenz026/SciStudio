// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
//
// Issue #1420 regression coverage: the default text-input branch of
// InlineConfigField was extracted into its own InlineTextInputField
// sub-component so that useState / useRef / useLayoutEffect now sit at the
// top level of every component in this file (rules-of-hooks). The behavior
// must stay identical:
//   - default text-input fields render an editable input,
//   - ui_widget="file_browser" / "directory_browser" still show the "..."
//     browse button next to the input, and
//   - ui_widget="directory_browser" still shows the clipboard-copy button.
//
// These tests exercise that the extracted component renders correctly in
// each branch, which transitively exercises that its hooks ran without
// throwing the React "Hooks called conditionally" error. Wave 2 (#1422)
// preserves the same discipline through the further split into
// BlockNode.parts/.

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { makeSchema, openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode - InlineTextInputField default-branch hook order (#1420)", () => {
  function renderField(uiWidget?: string) {
    return renderNode({
      category: "process",
      blockType: "field_block",
      schema: makeSchema({
        base_category: "process",
        type_name: "field_block",
        config_schema: {
          type: "object",
          properties: {
            path: {
              type: "string",
              ui_priority: 0,
              ...(uiWidget ? { ui_widget: uiWidget } : {}),
            },
          },
        },
      }),
    });
  }

  it("renders a plain text input when no ui_widget is set", () => {
    renderField();
    // A bare text input is rendered; no browse / clipboard buttons.
    expect(screen.queryByTitle("Browse filesystem")).toBeNull();
    expect(screen.queryByTitle(/Copy path/i)).toBeNull();
    // The text input itself is present.
    const input = document.querySelector('input[type="text"]') as HTMLInputElement | null;
    expect(input).not.toBeNull();
  });

  it("renders a Browse button when ui_widget is 'file_browser'", () => {
    renderField("file_browser");
    expect(screen.getByTitle("Browse filesystem")).toBeInTheDocument();
    // file_browser does NOT show the clipboard-copy button.
    expect(screen.queryByTitle(/Copy path/i)).toBeNull();
  });

  it("renders Browse + clipboard buttons when ui_widget is 'directory_browser'", () => {
    renderField("directory_browser");
    expect(screen.getByTitle("Browse filesystem")).toBeInTheDocument();
    expect(screen.getByTitle("Copy path to clipboard")).toBeInTheDocument();
  });
});
