import { describe, expect, it } from "vitest";

import type { BlockPortResponse, DynamicPortsConfig } from "../../types/api";
import { computeEffectivePorts } from "../computeEffectivePorts";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makePort(
  name: string,
  direction: "input" | "output",
  accepted: string[],
): BlockPortResponse {
  return {
    name,
    direction,
    accepted_types: accepted,
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

const CORE_TYPES = ["Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"] as const;

/** Mirrors the LoadData backend ``dynamic_ports`` ClassVar shape. */
const LOAD_DATA_DYNAMIC: DynamicPortsConfig = {
  source_config_key: "core_type",
  output_port_mapping: {
    data: {
      Array: ["Array"],
      DataFrame: ["DataFrame"],
      Series: ["Series"],
      Text: ["Text"],
      Artifact: ["Artifact"],
      CompositeData: ["CompositeData"],
    },
  },
};

/** Mirrors the SaveData backend ``dynamic_ports`` ClassVar shape. */
const SAVE_DATA_DYNAMIC: DynamicPortsConfig = {
  source_config_key: "core_type",
  input_port_mapping: {
    data: {
      Array: ["Array"],
      DataFrame: ["DataFrame"],
      Series: ["Series"],
      Text: ["Text"],
      Artifact: ["Artifact"],
      CompositeData: ["CompositeData"],
    },
  },
};

const LOAD_BASE_OUTPUT = [makePort("data", "output", ["DataObject"])];
const SAVE_BASE_INPUT = [makePort("data", "input", ["DataObject"])];

// ---------------------------------------------------------------------------
// Static-block fallthrough
// ---------------------------------------------------------------------------

describe("computeEffectivePorts — static block fallthrough", () => {
  it("returns the original ports when dynamicPorts is null", () => {
    const ports = [makePort("input", "input", ["Image"])];
    const result = computeEffectivePorts(null, "Array", ports, "input");
    // Identity preservation: static blocks must not pay any allocation cost.
    expect(result).toBe(ports);
  });

  it("returns the original ports when dynamicPorts is undefined", () => {
    const ports = [makePort("output", "output", ["Image"])];
    const result = computeEffectivePorts(undefined, "Array", ports, "output");
    expect(result).toBe(ports);
  });

  it("returns the original ports when configValue is undefined", () => {
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, undefined, LOAD_BASE_OUTPUT, "output");
    expect(result).toBe(LOAD_BASE_OUTPUT);
  });

  it("returns the original ports when configValue is the empty string", () => {
    // Empty string is falsy and should be treated like "unset".
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, "", LOAD_BASE_OUTPUT, "output");
    expect(result).toBe(LOAD_BASE_OUTPUT);
  });
});

// ---------------------------------------------------------------------------
// LoadData (output direction)
// ---------------------------------------------------------------------------

describe("computeEffectivePorts — LoadData (output mapping)", () => {
  it("resolves Array core_type to OutputPort accepted_types=['Array']", () => {
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, "Array", LOAD_BASE_OUTPUT, "output");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("data");
    expect(result[0].accepted_types).toEqual(["Array"]);
    // The original port object must NOT be mutated — defensive copy.
    expect(LOAD_BASE_OUTPUT[0].accepted_types).toEqual(["DataObject"]);
  });

  it("resolves DataFrame core_type to accepted_types=['DataFrame']", () => {
    const result = computeEffectivePorts(
      LOAD_DATA_DYNAMIC,
      "DataFrame",
      LOAD_BASE_OUTPUT,
      "output",
    );
    expect(result[0].accepted_types).toEqual(["DataFrame"]);
  });

  it.each(CORE_TYPES)("resolves %s core_type for LoadData", (coreType) => {
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, coreType, LOAD_BASE_OUTPUT, "output");
    expect(result[0].accepted_types).toEqual([coreType]);
  });

  it("preserves all non-accepted_types fields when overriding", () => {
    const port: BlockPortResponse = {
      name: "data",
      direction: "output",
      accepted_types: ["DataObject"],
      required: true,
      description: "Loaded data object",
      constraint_description: "single object",
      is_collection: false,
    };
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, "Series", [port], "output");
    expect(result[0]).toEqual({
      name: "data",
      direction: "output",
      accepted_types: ["Series"],
      required: true,
      description: "Loaded data object",
      constraint_description: "single object",
      is_collection: false,
    });
  });
});

// ---------------------------------------------------------------------------
// SaveData (input direction)
// ---------------------------------------------------------------------------

describe("computeEffectivePorts — SaveData (input mapping)", () => {
  it("resolves DataFrame core_type to InputPort accepted_types=['DataFrame']", () => {
    const result = computeEffectivePorts(SAVE_DATA_DYNAMIC, "DataFrame", SAVE_BASE_INPUT, "input");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("data");
    expect(result[0].accepted_types).toEqual(["DataFrame"]);
  });

  it.each(CORE_TYPES)("resolves %s core_type for SaveData", (coreType) => {
    const result = computeEffectivePorts(SAVE_DATA_DYNAMIC, coreType, SAVE_BASE_INPUT, "input");
    expect(result[0].accepted_types).toEqual([coreType]);
  });
});

// ---------------------------------------------------------------------------
// Graceful fallback for edge cases
// ---------------------------------------------------------------------------

describe("computeEffectivePorts — graceful fallback", () => {
  it("falls back to base ports for unknown enum value (does not throw)", () => {
    const result = computeEffectivePorts(
      LOAD_DATA_DYNAMIC,
      "UnknownType",
      LOAD_BASE_OUTPUT,
      "output",
    );
    expect(result).toHaveLength(1);
    // The unknown enum value yields the original placeholder, not an empty
    // accepted_types list and not an exception.
    expect(result[0].accepted_types).toEqual(["DataObject"]);
  });

  it("returns base ports when asking for input but only output_port_mapping is declared", () => {
    // LoadData declares output_port_mapping only. Asking for input direction
    // must NOT crash; it must fall through cleanly.
    const inputPorts = [makePort("data", "input", ["DataObject"])];
    const result = computeEffectivePorts(LOAD_DATA_DYNAMIC, "Array", inputPorts, "input");
    expect(result).toBe(inputPorts);
  });

  it("returns base ports when asking for output but only input_port_mapping is declared", () => {
    // Symmetric: SaveData declares input_port_mapping only.
    const result = computeEffectivePorts(SAVE_DATA_DYNAMIC, "Array", LOAD_BASE_OUTPUT, "output");
    expect(result).toBe(LOAD_BASE_OUTPUT);
  });

  it("leaves ports without rules unchanged in a multi-port block", () => {
    // A hypothetical block with TWO output ports where only ONE has dynamic
    // rules. The other port must pass through unmodified.
    const ports = [
      makePort("data", "output", ["DataObject"]),
      makePort("metadata", "output", ["Text"]),
    ];
    const partialDynamic: DynamicPortsConfig = {
      source_config_key: "core_type",
      output_port_mapping: {
        data: {
          Array: ["Array"],
        },
      },
    };
    const result = computeEffectivePorts(partialDynamic, "Array", ports, "output");
    expect(result).toHaveLength(2);
    // First port was overridden.
    expect(result[0].name).toBe("data");
    expect(result[0].accepted_types).toEqual(["Array"]);
    // Second port has no rule — must be the same object reference (no
    // unnecessary clone).
    expect(result[1]).toBe(ports[1]);
    expect(result[1].accepted_types).toEqual(["Text"]);
  });
});
