// Pure-unit tests for the helpers extracted into BlockNode.parts/.
// These exercise inputs the React-level tests cover only indirectly so the
// helpers stay verifiable on their own. Added as part of the #1422 split so
// every produced module owns at least one test file.

import { describe, expect, it } from "vitest";

import {
  capabilityLabel,
  capabilityWarning,
  getTopConfigProperties,
  selectedCapability,
} from "../../BlockNode.parts/inlineConfigHelpers";
import type { FormatCapabilityResponse } from "../../../../types/api";

function makeCap(overrides: Partial<FormatCapabilityResponse> = {}): FormatCapabilityResponse {
  return {
    id: "core.dataframe.csv.save",
    direction: "save",
    data_type: "DataFrame",
    format_id: "csv",
    extensions: [".csv"],
    label: "CSV",
    block_type: "SaveData",
    handler: "save",
    is_default: false,
    priority: 0,
    roundtrip_group: null,
    metadata_fidelity: {
      level: "typed_meta",
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

describe("getTopConfigProperties", () => {
  it("returns the top-3 properties sorted by ui_priority", () => {
    const result = getTopConfigProperties({
      properties: {
        c: { ui_priority: 3 },
        a: { ui_priority: 1 },
        b: { ui_priority: 2 },
        d: { ui_priority: 4 },
      },
    });
    expect(result.map((p) => p.key)).toEqual(["a", "b", "c"]);
  });

  it("treats missing ui_priority as 999", () => {
    const result = getTopConfigProperties({
      properties: {
        first: { ui_priority: 1 },
        last: {},
        middle: { ui_priority: 2 },
      },
    });
    expect(result.map((p) => p.key)).toEqual(["first", "middle", "last"]);
  });

  it("returns [] when no config schema is supplied", () => {
    expect(getTopConfigProperties(undefined)).toEqual([]);
    expect(getTopConfigProperties({})).toEqual([]);
  });
});

describe("capabilityLabel", () => {
  it("appends the extension list when present", () => {
    expect(capabilityLabel(makeCap({ label: "CSV", extensions: [".csv"] }))).toBe("CSV (.csv)");
  });

  it("returns the bare label when extensions is empty", () => {
    expect(capabilityLabel(makeCap({ label: "Pickle", extensions: [] }))).toBe("Pickle");
  });
});

describe("selectedCapability", () => {
  const a = makeCap({ id: "a" });
  const b = makeCap({ id: "b", is_default: true });
  const c = makeCap({ id: "c" });
  const caps = [a, b, c];

  it("returns the capability matching the supplied id", () => {
    expect(selectedCapability(caps, "a")).toBe(a);
  });

  it("returns the single capability when only one is available", () => {
    expect(selectedCapability([a], undefined)).toBe(a);
  });

  it("falls back to the is_default capability when id is unknown", () => {
    expect(selectedCapability(caps, "missing")).toBe(b);
  });

  it("returns undefined when no default and id is unknown", () => {
    expect(selectedCapability([a, c], undefined)).toBeUndefined();
  });
});

describe("capabilityWarning", () => {
  it("warns when multiple capabilities exist and none is selected", () => {
    const caps = [makeCap({ id: "x" }), makeCap({ id: "y" })];
    expect(capabilityWarning(caps, undefined)).toBe("Choose a format capability");
  });

  it("returns null when no capability and only one is available", () => {
    expect(capabilityWarning([makeCap()], undefined)).toBeNull();
  });

  it("warns on pixel_only save fidelity", () => {
    const cap = makeCap({
      metadata_fidelity: {
        level: "pixel_only",
        typed_meta_reads: [],
        typed_meta_writes: [],
        format_metadata_reads: [],
        format_metadata_writes: [],
        notes: null,
      },
    });
    expect(capabilityWarning([cap], cap)).toMatch(/typed metadata may not be written/);
  });

  it("warns when the capability is a migration scaffold", () => {
    const cap = makeCap({ migration_scaffold: true });
    expect(capabilityWarning([cap], cap)).toBe("Legacy synthesized capability");
  });

  it("returns null for a clean capability", () => {
    const cap = makeCap();
    expect(capabilityWarning([cap], cap)).toBeNull();
  });
});
