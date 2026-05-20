// ADR-043 FR-012 — CapabilityDropdown unit tests.
//
// Exercises the auto-select rule (single match), the placeholder/empty
// states, the metadata-fidelity badge, and basic onChange wiring. The
// component accepts a `loadCapabilities` injection so we never mock fetch.

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapabilityDropdown } from "../components/PortEditor/CapabilityDropdown";
import type { FormatCapabilityResponse } from "../types/api";

function fakeCapability(
  id: string,
  overrides: Partial<FormatCapabilityResponse> = {},
): FormatCapabilityResponse {
  return {
    id,
    direction: "save",
    data_type: "Image",
    format_id: id.split(".").slice(-2)[0] ?? "tiff",
    extensions: ["tif", "tiff"],
    label: `Capability ${id}`,
    block_type: "SaveImage",
    handler: "tifffile",
    is_default: false,
    priority: 0,
    roundtrip_group: null,
    metadata_fidelity: {
      level: "pixel_only",
      typed_meta_reads: [],
      typed_meta_writes: [],
      format_metadata_reads: [],
      format_metadata_writes: [],
      notes: null,
    },
    is_synthesized: false,
    migration_scaffold: false,
    ...overrides,
  };
}

describe("CapabilityDropdown", () => {
  afterEach(() => {
    cleanup();
  });

  it("auto-selects when exactly one capability matches (FR-012)", async () => {
    const only = fakeCapability("imaging.image.tiff.save", {
      metadata_fidelity: {
        level: "format_specific",
        typed_meta_reads: [],
        typed_meta_writes: ["pixels.physical_size_x"],
        format_metadata_reads: ["ome"],
        format_metadata_writes: ["ome"],
        notes: null,
      },
    });
    const loadCapabilities = vi.fn().mockResolvedValue([only]);
    const onChange = vi.fn();

    render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tif"
        value={null}
        onChange={onChange}
        loadCapabilities={loadCapabilities}
      />,
    );

    await waitFor(() => {
      expect(loadCapabilities).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith("imaging.image.tiff.save");
    });
  });

  it("renders multiple options without auto-selecting (FR-012 ambiguity)", async () => {
    const tif = fakeCapability("imaging.image.tiff.save");
    const ome = fakeCapability("imaging.image.ome-tiff.save", {
      label: "OME-TIFF saver",
      format_id: "ome-tiff",
      metadata_fidelity: {
        level: "lossless",
        typed_meta_reads: [],
        typed_meta_writes: [],
        format_metadata_reads: [],
        format_metadata_writes: [],
        notes: null,
      },
    });
    const loadCapabilities = vi.fn().mockResolvedValue([tif, ome]);
    const onChange = vi.fn();

    render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tif"
        value={null}
        onChange={onChange}
        loadCapabilities={loadCapabilities}
      />,
    );

    await waitFor(() => {
      expect(loadCapabilities).toHaveBeenCalledTimes(1);
    });
    // No auto-select with >1 option.
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(/2 capabilities match/)).toBeInTheDocument();
    // Both options are rendered.
    expect(
      screen.getByRole("option", { name: /imaging\.image\.ome-tiff\.save|OME-TIFF saver/i }),
    ).toBeInTheDocument();
  });

  it("calls onChange with the picked id when user selects an option", async () => {
    const tif = fakeCapability("imaging.image.tiff.save");
    const ome = fakeCapability("imaging.image.ome-tiff.save", {
      label: "OME-TIFF saver",
      format_id: "ome-tiff",
    });
    const loadCapabilities = vi.fn().mockResolvedValue([tif, ome]);
    const onChange = vi.fn();

    render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tif"
        value={null}
        onChange={onChange}
        loadCapabilities={loadCapabilities}
      />,
    );

    await waitFor(() => {
      expect(loadCapabilities).toHaveBeenCalled();
    });

    // P1-01 (Phase C1 audit follow-up, issue #1296):
    // The `loadCapabilities` mock resolves before React has flushed the
    // post-fetch re-render that materialises the `<option>` children. If
    // we fire `change` immediately, the requested option is not yet in
    // the DOM and the synthetic event sets `select.value` to `""`,
    // which the component's `onChange` handler ignores (early `if
    // (!nextId) return` guard) — the assertion below then fails on
    // faster CI shards even though the production code is correct.
    // Wait for the option's visible label to render before firing.
    const select = await waitFor(() => screen.getByRole("combobox") as HTMLSelectElement);
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: /imaging\.image\.ome-tiff\.save|OME-TIFF saver/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.change(select, { target: { value: "imaging.image.ome-tiff.save" } });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith("imaging.image.ome-tiff.save");
    });
  });

  it("disables the select while extension is empty", () => {
    const loadCapabilities = vi.fn().mockResolvedValue([]);
    render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension=""
        value={null}
        onChange={() => {}}
        loadCapabilities={loadCapabilities}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select).toBeDisabled();
    expect(screen.getByText(/Enter extension/i)).toBeInTheDocument();
  });

  it("renders a metadata-fidelity badge for the selected capability", async () => {
    const cap = fakeCapability("imaging.image.tiff.save", {
      metadata_fidelity: {
        level: "lossless",
        typed_meta_reads: [],
        typed_meta_writes: [],
        format_metadata_reads: [],
        format_metadata_writes: [],
        notes: null,
      },
    });
    const loadCapabilities = vi.fn().mockResolvedValue([cap]);

    render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tif"
        value="imaging.image.tiff.save"
        onChange={() => {}}
        loadCapabilities={loadCapabilities}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("fidelity-badge")).toHaveTextContent("lossless");
    });
  });

  it("ignores stale fetch responses (out-of-order responses do not clobber)", async () => {
    const firstResp: FormatCapabilityResponse[] = [fakeCapability("a")];
    const secondResp: FormatCapabilityResponse[] = [
      fakeCapability("b"),
      fakeCapability("c"),
    ];

    let resolveFirst!: (v: FormatCapabilityResponse[]) => void;
    const firstPromise = new Promise<FormatCapabilityResponse[]>((resolve) => {
      resolveFirst = resolve;
    });
    let callCount = 0;
    const loadCapabilities = vi.fn(() => {
      callCount += 1;
      return callCount === 1 ? firstPromise : Promise.resolve(secondResp);
    });

    const { rerender } = render(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tif"
        value={null}
        onChange={() => {}}
        loadCapabilities={loadCapabilities}
      />,
    );

    // Trigger a second fetch by changing the extension.
    rerender(
      <CapabilityDropdown
        direction="save"
        dataType="Image"
        extension="tiff"
        value={null}
        onChange={() => {}}
        loadCapabilities={loadCapabilities}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByRole("option", { name: /Capability b/i })).toBeInTheDocument();
    });

    // Now resolve the stale first request — must NOT swap the list back.
    resolveFirst(firstResp);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("option", { name: /Capability a/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Capability b/i })).toBeInTheDocument();
  });
});
