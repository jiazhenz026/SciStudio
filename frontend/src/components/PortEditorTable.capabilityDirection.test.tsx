// Regression for the ADR-043 boundary-IO direction inversion bug.
//
// At a block's IO boundary the runtime direction is inverted: an INPUT port is
// fed by a SAVER (SciStudio writes the DataObject to a file for the external
// app) and an OUTPUT port is filled by a LOADER (the external app writes a file
// SciStudio reads back). The validator checks output ports with
// find_loader_capability(direction="load").
//
// A previous version of PortEditorTable passed direction="save" for output
// ports, so the capability dropdown listed savers and auto-pinned (e.g.)
// core.series.csv.save on a Series/.csv output port. The backend then rejected
// the workflow ("Capability id exists but does not satisfy the requested IO
// contract: direction='load' ... capability_id='core.series.csv.save'"). This
// test pins the corrected direction so the inversion cannot regress.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { capturedProps } = vi.hoisted(() => ({
  capturedProps: [] as Array<{ direction?: string; extension?: string }>,
}));

vi.mock("./PortEditor/CapabilityDropdown", () => ({
  CapabilityDropdown: (props: { direction?: string; extension?: string }) => {
    capturedProps.push(props);
    return null;
  },
}));

import { type PortRow, PortEditorTable } from "./PortEditorTable";

const TYPE_HIERARCHY = [{ name: "Series", base_type: "DataObject", description: "" }];

describe("PortEditorTable capability direction (ADR-043 boundary IO)", () => {
  afterEach(() => {
    cleanup();
    capturedProps.length = 0;
  });

  it("passes direction='load' to the CapabilityDropdown for output ports", () => {
    const ports: PortRow[] = [{ name: "table", types: ["Series"], extension: "csv" }];
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={() => {}}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const dropdownProps = capturedProps.find((props) => props.direction !== undefined);
    expect(dropdownProps?.direction).toBe("load");
  });

  it("normalises the stored extension (leading dot stripped) for the dropdown", () => {
    // The extension input now preserves a raw ".CSV", but the capability lookup
    // must still receive the normalised "csv".
    const ports: PortRow[] = [{ name: "table", types: ["Series"], extension: ".CSV" }];
    render(
      <PortEditorTable
        allowedTypes={[]}
        direction="output"
        onChange={() => {}}
        ports={ports}
        typeHierarchy={TYPE_HIERARCHY}
      />,
    );

    const dropdownProps = capturedProps.find((props) => props.extension !== undefined);
    expect(dropdownProps?.extension).toBe("csv");
  });
});
