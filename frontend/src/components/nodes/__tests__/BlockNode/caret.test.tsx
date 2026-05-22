// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
// Covers caret-preservation behavior in the default text-input branch of
// InlineConfigField (issue #710) and the audit follow-up that ensures the
// stale post-edit caret is NOT replayed on unrelated re-renders.

import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";

import { BlockNode } from "../../BlockNode";
import type { BlockNodeData } from "../../../../types/ui";

import { makeSchema, openNativeDialogMock, reactNativeInputChange } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("InlineConfigField - caret preservation on mid-string insert (#710)", () => {
  // Wrapper that re-renders the BlockNode whenever onUpdateConfig is called,
  // simulating the Zustand-store round-trip that triggers the original caret-
  // reset bug in React-controlled inputs.
  function StatefulHost({ initial }: { initial: string }) {
    const [config, setConfig] = useState<Record<string, unknown>>({ path: initial });
    const baseData: BlockNodeData = {
      label: "Test Block",
      blockType: "test_block",
      category: "process",
      inputPorts: [],
      outputPorts: [],
      config,
      schema: makeSchema({
        config_schema: {
          type: "object",
          properties: { path: { type: "string", title: "Path", ui_priority: 0 } },
        },
      }),
      onUpdateConfig: (patch: Record<string, unknown>) => {
        setConfig((c) => ({ ...c, ...patch }));
      },
    };
    const props = {
      id: "node-1",
      type: "block",
      data: baseData,
      selected: false,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      zIndex: 0,
    } as Parameters<typeof BlockNode>[0];
    return (
      <ReactFlowProvider>
        <BlockNode {...props} />
      </ReactFlowProvider>
    );
  }

  it("inserts a character in the middle of the value without jumping caret to end", () => {
    render(<StatefulHost initial="abcdef" />);
    const input = screen.getByDisplayValue("abcdef") as HTMLInputElement;

    // Focus the input and place the caret between "abc" and "def".
    act(() => {
      input.focus();
      input.setSelectionRange(3, 3);
    });
    expect(document.activeElement).toBe(input);
    expect(input.selectionStart).toBe(3);

    // Simulate the browser inserting "X" at position 3 by dispatching a
    // change event whose target reflects the would-be post-input state.
    // We must also set the DOM selectionStart/selectionEnd because the
    // production onChange reads them off the event target.
    act(() => {
      input.value = "abcXdef";
      input.setSelectionRange(4, 4);
      fireEvent.change(input, { target: input });
    });

    // After the round-trip (state update -> re-render with new value prop),
    // the caret must remain at position 4, not jump to the end (7).
    const updated = screen.getByDisplayValue("abcXdef") as HTMLInputElement;
    expect(updated).toBe(input); // same DOM node, just re-rendered
    expect(updated.selectionStart).toBe(4);
    expect(updated.selectionEnd).toBe(4);
    expect(updated.selectionStart).not.toBe(updated.value.length);
  });
});

describe("InlineConfigField - does NOT restore stale caret on unrelated re-render after caret moved without value change (#710 audit follow-up)", () => {
  // Variant of StatefulHost that exposes a setter for an unrelated state
  // value, so a test can force a re-render WITHOUT firing onChange on the
  // input. This is the exact scenario the audit identified: the user
  // types once (refreshing selectionRef), then moves the caret with the
  // mouse, then some sibling state in the parent triggers a re-render.
  // The pre-fix code would force the caret back to the stale post-edit
  // position; the fix nulls the pending selection after every layout
  // effect so it does not.
  let forceRerender: (() => void) | null = null;
  function StatefulHostWithSibling({ initial }: { initial: string }) {
    const [config, setConfig] = useState<Record<string, unknown>>({ path: initial });
    const [, setTick] = useState(0);
    forceRerender = () => setTick((n) => n + 1);
    const baseData: BlockNodeData = {
      label: "Test Block",
      blockType: "test_block",
      category: "process",
      inputPorts: [],
      outputPorts: [],
      config,
      schema: makeSchema({
        config_schema: {
          type: "object",
          properties: { path: { type: "string", title: "Path", ui_priority: 0 } },
        },
      }),
      onUpdateConfig: (patch: Record<string, unknown>) => {
        setConfig((c) => ({ ...c, ...patch }));
      },
    };
    const props = {
      id: "node-1",
      type: "block",
      data: baseData,
      selected: false,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      zIndex: 0,
    } as Parameters<typeof BlockNode>[0];
    return (
      <ReactFlowProvider>
        <BlockNode {...props} />
      </ReactFlowProvider>
    );
  }

  it("keeps caret at user-moved position when unrelated re-render fires", () => {
    forceRerender = null;
    // Seed initial value to "abcXdef" directly: this simulates the
    // post-typing state. The bug under test is independent of whether the
    // value got there by typing or by initial render — what matters is:
    //   (a) the input fires onChange at least once (refreshing the captured
    //       caret position), AND
    //   (b) the user then moves the caret without changing the value, AND
    //   (c) an unrelated re-render fires while the field is still focused.
    // Reproducing all three steps explicitly below isolates the regression
    // from any unrelated mechanics of fireEvent.change + controlled inputs.
    render(<StatefulHostWithSibling initial="abcXdef" />);
    const input = screen.getByDisplayValue("abcXdef") as HTMLInputElement;

    // (a) Focus, then fire a real React-recognised input event that
    // actually reaches the production onChange handler. We type the
    // sequence "abcXdef" -> "abcXYdef" -> "abcXdef" so the captured
    // selection ref ends up as (4, 4) — i.e. the post-edit caret
    // position. This is critical: setting input.value directly bypasses
    // React's controlled-input tracker, so the onChange handler never
    // fires and the bug never arms. reactNativeInputChange() uses the
    // native value setter trick so React DOES see the change.
    act(() => {
      input.focus();
      input.setSelectionRange(4, 4);
    });
    act(() => {
      reactNativeInputChange(input, "abcXYdef", 5);
    });
    act(() => {
      reactNativeInputChange(input, "abcXdef", 4);
    });
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("abcXdef");
    expect(input.selectionStart).toBe(4);

    // (b) User moves caret manually (no value change, no onChange).
    act(() => {
      input.setSelectionRange(1, 1);
    });
    expect(input.selectionStart).toBe(1);

    // (c) Unrelated parent re-render — DO NOT fire change on the input.
    act(() => {
      forceRerender?.();
    });

    // Regression assertion: caret stays at 1, value unchanged. Pre-fix,
    // the layout effect would replay the stale {start: 4, end: 4}
    // selection captured in step (a), snapping the caret back to 4. The
    // fix nulls pendingSelectionRef at the end of every layout effect,
    // so any subsequent unrelated render is a no-op for selection.
    const afterRerender = screen.getByDisplayValue("abcXdef") as HTMLInputElement;
    expect(afterRerender).toBe(input);
    expect(afterRerender.value).toBe("abcXdef");
    expect(afterRerender.selectionStart).toBe(1);
    expect(afterRerender.selectionEnd).toBe(1);
    // Stronger: caret must not be back at the stale post-edit position.
    expect(afterRerender.selectionStart).not.toBe(4);
  });
});
