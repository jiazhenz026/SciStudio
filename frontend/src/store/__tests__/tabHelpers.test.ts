import { describe, expect, it } from "vitest";

import { languageForPath } from "../tabSlice.parts/tabHelpers";

describe("tabHelpers", () => {
  it("maps R scripts to Monaco's R language id", () => {
    expect(languageForPath("plots/qc/render.R")).toBe("r");
    expect(languageForPath("plots/qc/render.r")).toBe("r");
  });
});
