// Tests for the #1325 AddPortDialog UX.
//
// Verifies: default name + first allowed type pre-fill, name editing,
// type-picker change, submit / cancel behaviour, Enter / Escape
// keyboard handling.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddPortDialog } from "../BlockNode.parts/AddPortDialog";

const TYPE_HIERARCHY = [
  { name: "DataObject", base_type: null, description: "" },
  { name: "Image", base_type: "DataObject", description: "" },
  { name: "DataFrame", base_type: "DataObject", description: "" },
];

describe("AddPortDialog", () => {
  afterEach(() => {
    cleanup();
  });

  it("pre-fills name + first allowed type", () => {
    render(
      <AddPortDialog
        direction="input"
        allowedTypes={["Image", "DataFrame"]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName="port_3"
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    );
    const nameInput = screen.getByTestId("add-port-name") as HTMLInputElement;
    const typeSelect = screen.getByTestId("add-port-type") as HTMLSelectElement;
    expect(nameInput.value).toBe("port_3");
    expect(typeSelect.value).toBe("Image");
  });

  it("falls back to type hierarchy when allowedTypes is empty", () => {
    render(
      <AddPortDialog
        direction="output"
        allowedTypes={[]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName="port_1"
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    );
    const typeSelect = screen.getByTestId("add-port-type") as HTMLSelectElement;
    // First hierarchy entry is DataObject — used as default when no
    // explicit allowedTypes constraint.
    expect(typeSelect.value).toBe("DataObject");
  });

  it("calls onSubmit with trimmed name + selected type", () => {
    const onSubmit = vi.fn();
    render(
      <AddPortDialog
        direction="input"
        allowedTypes={["Image", "DataFrame"]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName="port_1"
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );
    const nameInput = screen.getByTestId("add-port-name") as HTMLInputElement;
    const typeSelect = screen.getByTestId("add-port-type") as HTMLSelectElement;

    fireEvent.change(nameInput, { target: { value: "  raw_image  " } });
    fireEvent.change(typeSelect, { target: { value: "DataFrame" } });
    fireEvent.click(screen.getByTestId("add-port-submit"));

    expect(onSubmit).toHaveBeenCalledWith("raw_image", "DataFrame");
  });

  it("submit button is disabled when name is blank", () => {
    render(
      <AddPortDialog
        direction="input"
        allowedTypes={["Image"]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName=""
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    );
    const submit = screen.getByTestId("add-port-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("Escape key fires onCancel", () => {
    const onCancel = vi.fn();
    render(
      <AddPortDialog
        direction="input"
        allowedTypes={["Image"]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName="port_1"
        onCancel={onCancel}
        onSubmit={() => {}}
      />,
    );
    fireEvent.keyDown(screen.getByTestId("add-port-name"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });

  it("Enter key submits when name is non-blank", () => {
    const onSubmit = vi.fn();
    render(
      <AddPortDialog
        direction="input"
        allowedTypes={["Image"]}
        typeHierarchy={TYPE_HIERARCHY}
        defaultName="port_1"
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.keyDown(screen.getByTestId("add-port-name"), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith("port_1", "Image");
  });
});
