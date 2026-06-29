import { describe, expect, it } from "vitest";

import {
  ALL_SYMBOLS,
  CANONICAL_ROOTS,
  charBeforeWord,
  detectImportRoot,
  hoverMarkdownFor,
  suggestApiSymbols,
} from "./apiCompletions";

describe("apiCompletions manifest", () => {
  it("loads the generated public surface", () => {
    expect(CANONICAL_ROOTS).toContain("scistudio.blocks.base");
    expect(CANONICAL_ROOTS).toContain("scistudio.core.types");
    // The standardized reference covers 138 symbols across 9 roots (#1875).
    expect(CANONICAL_ROOTS.length).toBe(9);
    expect(ALL_SYMBOLS.length).toBeGreaterThanOrEqual(130);
  });

  it("carries signatures and stability for known symbols", () => {
    const block = ALL_SYMBOLS.find((s) => s.name === "Block");
    expect(block?.module).toBe("scistudio.blocks.base");
    const array = ALL_SYMBOLS.find((s) => s.name === "Array");
    expect(array?.signature).toContain("axes");
    expect(array?.stability).toBe("stable");
  });
});

describe("charBeforeWord", () => {
  it("detects member access vs bare identifier", () => {
    expect(charBeforeWord("    df.to_mem")).toBe(".");
    expect(charBeforeWord("Bl")).toBe("");
    expect(charBeforeWord("    Bl")).toBe(" ");
    expect(charBeforeWord("x = Arr")).toBe(" ");
  });
});

describe("detectImportRoot", () => {
  it("recognizes a known canonical import root", () => {
    expect(detectImportRoot("from scistudio.blocks.base import Bl")).toBe("scistudio.blocks.base");
    expect(detectImportRoot("from scistudio.core.types import ")).toBe("scistudio.core.types");
  });

  it("returns null for non-roots or non-import lines", () => {
    expect(detectImportRoot("from scistudio.not.a.root import X")).toBeNull();
    expect(detectImportRoot("Block")).toBeNull();
    expect(detectImportRoot("import os")).toBeNull();
  });
});

describe("suggestApiSymbols", () => {
  it("offers the full public surface in general code context", () => {
    const labels = suggestApiSymbols({ linePrefix: "    Bl" }).map((s) => s.label);
    expect(labels).toContain("Block");
    expect(labels).toContain("Array");
    expect(labels).toContain("InputPort");
    // The Block scaffold snippet is offered alongside symbols.
    expect(labels).toContain("sci-block");
  });

  it("restricts suggestions to the root inside an import clause", () => {
    const specs = suggestApiSymbols({ linePrefix: "from scistudio.core.types import " });
    const labels = specs.map((s) => s.label);
    expect(labels).toContain("Array");
    expect(labels).toContain("DataFrame");
    // base-only symbols and the scaffold must not leak into a types import.
    expect(labels).not.toContain("Block");
    expect(labels).not.toContain("sci-block");
  });

  it("does not fire on member access (out of scope for Plan A)", () => {
    expect(suggestApiSymbols({ linePrefix: "    df." })).toEqual([]);
    expect(suggestApiSymbols({ linePrefix: "    df.to_mem" })).toEqual([]);
  });

  it("includes module + stability in the completion detail", () => {
    const block = suggestApiSymbols({ linePrefix: "Bl" }).find((s) => s.label === "Block");
    expect(block?.detail).toContain("scistudio.blocks.base");
  });
});

describe("hoverMarkdownFor", () => {
  it("returns rich markdown for a public symbol", () => {
    const md = hoverMarkdownFor("Block");
    expect(md).not.toBeNull();
    expect(md).toContain("scistudio.blocks.base");
    expect(md).toContain("```python");
  });

  it("returns null for unknown words", () => {
    expect(hoverMarkdownFor("not_a_scistudio_symbol")).toBeNull();
  });
});
