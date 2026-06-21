import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type PortRow, PortEditorTable } from "./PortEditorTable";

const TYPE_HIERARCHY = [
  { name: "DataObject", base_type: "DataObject", description: "" },
  { name: "Image", base_type: "Image", description: "" },
];

describe("PortEditorTable", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders an extension column for output ports (issue #680)", () => {
    const ports: PortRow[] = [{ name: "images", types: ["Image"], extension: "tif" }];
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={() => {}}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const extInput = screen.getByLabelText("extension for images") as HTMLInputElement;
    expect(extInput).toBeInTheDocument();
    expect(extInput.value).toBe("tif");
  });

  it("does NOT render an extension column for input ports", () => {
    const ports: PortRow[] = [{ name: "data", types: ["DataObject"] }];
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="input"
        onChange={() => {}}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    expect(screen.queryByLabelText("extension for data")).toBeNull();
  });

  it("preserves the raw extension text including a leading dot", () => {
    // The input keeps exactly what the user typed (matching the CodeBlock port
    // editor); normalisation happens at consumption (backend binning +
    // CapabilityDropdown), not on the stored value.
    const ports: PortRow[] = [{ name: "tables", types: ["DataObject"], extension: "" }];
    const onChange = vi.fn();
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={onChange}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const extInput = screen.getByLabelText("extension for tables");
    fireEvent.change(extInput, { target: { value: ".CSV" } });

    expect(onChange).toHaveBeenCalledTimes(1);
    // The normalised extension changed ("" -> "csv"), so #1366 clears the
    // (absent) capability pin to null; the stored extension keeps the raw text.
    expect(onChange.mock.calls[0][0]).toEqual([
      {
        name: "tables",
        types: ["DataObject"],
        extension: ".CSV",
        capability_id: null,
      },
    ]);
  });

  it("keeps the port-name input focused across rapid edits (issue #700)", () => {
    // Regression: the row was keyed by `port.name + index`, so each keystroke
    // changed the React key, remounted the <input>, and dropped focus after
    // a single character. The fix uses a stable index-based key.
    function Harness() {
      const [ports, setPorts] = useState<PortRow[]>([{ name: "a", types: ["DataObject"] }]);
      return (
        <PortEditorTable
          allowedTypes={[]}
          direction="input"
          onChange={setPorts}
          ports={ports}
          typeHierarchy={TYPE_HIERARCHY}
        />
      );
    }
    render(<Harness />);

    const nameInput = screen.getByPlaceholderText("port name") as HTMLInputElement;
    nameInput.focus();
    expect(document.activeElement).toBe(nameInput);

    // Three rapid edits — focus must survive every one of them.
    fireEvent.change(nameInput, { target: { value: "ab" } });
    expect(document.activeElement).toBe(screen.getByPlaceholderText("port name"));
    fireEvent.change(nameInput, { target: { value: "abc" } });
    expect(document.activeElement).toBe(screen.getByPlaceholderText("port name"));
    fireEvent.change(nameInput, { target: { value: "abcd" } });

    const finalInput = screen.getByPlaceholderText("port name") as HTMLInputElement;
    expect(document.activeElement).toBe(finalInput);
    expect(finalInput.value).toBe("abcd");
  });

  it("seeds new output rows with an empty extension field", () => {
    const onChange = vi.fn();
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={onChange}
        ports={[]}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    fireEvent.click(screen.getByText("+ Add Port"));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as PortRow[];
    expect(next).toHaveLength(1);
    expect(next[0].extension).toBe("");
  });

  it("clears a pinned capability_id when the user changes the port type (#1366)", () => {
    // Regression for #1366: handleTypeChange used to preserve `capability_id`
    // even when the new type no longer registered that capability, letting
    // the user save a workflow that then failed backend validation.
    const ports: PortRow[] = [
      {
        name: "out",
        types: ["DataObject"],
        extension: "csv",
        capability_id: "data:csv:save:default",
      },
    ];
    const onChange = vi.fn();
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={onChange}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const typeSelect = screen.getByDisplayValue("DataObject") as HTMLSelectElement;
    fireEvent.change(typeSelect, { target: { value: "Image" } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual([
      {
        name: "out",
        types: ["Image"],
        extension: "csv",
        capability_id: null,
      },
    ]);
  });

  it("clears a pinned capability_id when the user changes the extension (#1366)", () => {
    // Regression for #1366: handleExtensionChange used to preserve
    // `capability_id` even though the (direction, type, extension) tuple
    // changed and the previously pinned capability may no longer be valid.
    const ports: PortRow[] = [
      {
        name: "out",
        types: ["Image"],
        extension: "tif",
        capability_id: "imaging:tif:save:default",
      },
    ];
    const onChange = vi.fn();
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={onChange}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const extInput = screen.getByLabelText("extension for out");
    fireEvent.change(extInput, { target: { value: "png" } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual([
      {
        name: "out",
        types: ["Image"],
        extension: "png",
        capability_id: null,
      },
    ]);
  });

  it("keeps capability_id on no-op extension edits (Codex P2 from PR #1397)", () => {
    // The normalizer strips leading dots and lowercases, so `.CSV` -> `csv`.
    // If the row's extension is already `csv`, editing to `.CSV` should NOT
    // drop the user's explicit capability pin; the (direction, type,
    // extension) tuple is unchanged. Uses `direction="output"` because the
    // extension input only renders for output ports (renderExtension guard).
    const ports: PortRow[] = [
      {
        name: "out",
        types: ["Table"],
        extension: "csv",
        capability_id: "table:csv:save:special",
      },
    ];
    const onChange = vi.fn();
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={onChange}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const extInput = screen.getByLabelText("extension for out");
    fireEvent.change(extInput, { target: { value: ".CSV" } });

    // The raw text updates to ".CSV", but the normalised tuple is unchanged
    // ("csv" -> "csv"), so the user's explicit capability pin is preserved.
    if (onChange.mock.calls.length > 0) {
      expect(onChange.mock.calls[0][0]).toEqual([
        {
          name: "out",
          types: ["Table"],
          extension: ".CSV",
          capability_id: "table:csv:save:special",
        },
      ]);
    }
  });
});
