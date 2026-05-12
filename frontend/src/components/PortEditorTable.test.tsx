import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
    const ports: PortRow[] = [
      { name: "images", types: ["Image"], extension: "tif" },
    ];
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

  it("normalises typed extensions: lowercases and strips leading dots", () => {
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
    expect(onChange.mock.calls[0][0]).toEqual([
      { name: "tables", types: ["DataObject"], extension: "csv" },
    ]);
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
});
