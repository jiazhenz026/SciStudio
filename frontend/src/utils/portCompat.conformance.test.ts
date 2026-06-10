/**
 * Port-compat conformance test (#1548 / DSN-9).
 *
 * ``portCompat.ts`` hand-mirrors the backend
 * ``scistudio.blocks.base.ports.validate_connection`` with no shared
 * fixture, so the two can silently drift. This test pins the frontend
 * behaviour against a committed golden oracle generated FROM the backend.
 *
 * Oracle source: ``__fixtures__/portcompat.oracle.json``, produced by
 * ``__fixtures__/generate_portcompat_oracle.py`` (which runs the real
 * backend ``validate_connection`` over a fixed set of connection
 * attempts). Regenerate the JSON via that script whenever the backend
 * rule or the core type hierarchy changes; the matching pytest
 * (``test_portcompat_oracle.py``) guards the JSON against backend drift.
 */
import { describe, expect, it } from "vitest";

import type { TypeHierarchyEntry } from "../types/api";

import oracle from "./__fixtures__/portcompat.oracle.json";
import { arePortTypesCompatible } from "./portCompat";

interface OracleCase {
  source_accepted_types: string[];
  target_accepted_types: string[];
  expected_compatible: boolean;
}

interface Oracle {
  source: string;
  type_hierarchy: TypeHierarchyEntry[];
  cases: OracleCase[];
}

const typedOracle = oracle as unknown as Oracle;

describe("portCompat conformance against backend oracle (#1548)", () => {
  it("the oracle is non-trivial (covers both verdicts)", () => {
    expect(typedOracle.cases.length).toBeGreaterThan(20);
    const verdicts = new Set(typedOracle.cases.map((c) => c.expected_compatible));
    expect(verdicts.has(true)).toBe(true);
    expect(verdicts.has(false)).toBe(true);
  });

  it.each(typedOracle.cases)(
    "$source_accepted_types -> $target_accepted_types == $expected_compatible",
    ({ source_accepted_types, target_accepted_types, expected_compatible }) => {
      const actual = arePortTypesCompatible(
        source_accepted_types,
        target_accepted_types,
        typedOracle.type_hierarchy,
      );
      expect(actual).toBe(expected_compatible);
    },
  );
});
