// ADR-053 FR-022 — the static import parse behind cascade detection.

import { describe, expect, it } from "vitest";

import { importedModuleRoots, importedSymbols, parseImports } from "../pythonImports";

describe("parseImports — FR-022 static extraction", () => {
  it("reads plain, aliased, and comma-separated imports", () => {
    const parsed = parseImports("import spectrum\nimport trace as t, other\nimport pkg.sub\n");
    expect(parsed.map((entry) => entry.module)).toEqual(["spectrum", "trace", "other", "pkg.sub"]);
    expect(importedModuleRoots(parsed)).toEqual(new Set(["spectrum", "trace", "other", "pkg"]));
  });

  it("reads `from … import` names, aliases resolved", () => {
    const parsed = parseImports("from spectrum import Spectrum as S, Trace\n");
    expect(parsed).toEqual([{ module: "spectrum", names: ["Spectrum", "Trace"] }]);
    expect(importedSymbols(parsed)).toEqual(new Set(["Spectrum", "Trace"]));
  });

  it("joins parenthesised and backslash continuations into one statement", () => {
    const parsed = parseImports("from spectrum import (\n    Spectrum,\n    Trace,\n)\n");
    expect(parsed).toEqual([{ module: "spectrum", names: ["Spectrum", "Trace"] }]);
    expect(parseImports("from spectrum import \\\n    Spectrum\n")).toEqual([
      { module: "spectrum", names: ["Spectrum"] },
    ]);
  });

  it("catches imports nested inside try blocks and functions", () => {
    const parsed = parseImports(
      "try:\n    from spectrum import Spectrum\nexcept ImportError:\n    pass\n",
    );
    expect(importedModuleRoots(parsed)).toEqual(new Set(["spectrum"]));
  });

  it("strips leading dots from a relative import but keeps the module", () => {
    expect(parseImports("from .spectrum import Spectrum")).toEqual([
      { module: "spectrum", names: ["Spectrum"] },
    ]);
  });

  it("treats a wildcard as a module import with no bound names", () => {
    expect(parseImports("from spectrum import *")).toEqual([{ module: "spectrum", names: [] }]);
  });

  it("ignores imports written inside a docstring", () => {
    const source = [
      '"""Example:',
      "",
      "    from spectrum import Spectrum",
      '"""',
      "import numpy",
    ].join("\n");
    expect(importedModuleRoots(parseImports(source))).toEqual(new Set(["numpy"]));
  });

  it("ignores commented-out imports", () => {
    expect(parseImports("# from spectrum import Spectrum\nimport numpy")).toEqual([
      { module: "numpy", names: [] },
    ]);
  });

  it("returns nothing for a file with no imports", () => {
    expect(parseImports("class Foo:\n    pass\n")).toEqual([]);
  });
});
