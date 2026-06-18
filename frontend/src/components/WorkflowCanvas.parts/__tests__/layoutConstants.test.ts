import { describe, expect, it } from "vitest";

import {
  GROUP_PADDING,
  HIGH_DEGREE_CLEARANCE,
  LAYER_GAP,
  NODE_SIZE,
  SIBLING_GAP,
} from "../layoutConstants";

describe("layoutConstants (ADR-050 §2.1 / §3.2)", () => {
  it("declares NODE_SIZE === 104 to match nodeGeometry.NODE_SIZE", () => {
    // Decoupled-on-purpose invariant (dispatch checklist §4.1): this file and
    // FE-1's nodeGeometry.ts each declare their own NODE_SIZE; both MUST be 104.
    expect(NODE_SIZE).toBe(104);
  });

  it("exposes deterministic positive spacing constants", () => {
    for (const value of [LAYER_GAP, SIBLING_GAP, HIGH_DEGREE_CLEARANCE, GROUP_PADDING]) {
      expect(typeof value).toBe("number");
      expect(Number.isFinite(value)).toBe(true);
      expect(value).toBeGreaterThan(0);
    }
  });
});
