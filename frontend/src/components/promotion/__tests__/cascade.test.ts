// ADR-053 §6.1 — cascade dependency resolution (FR-021 – FR-024).

import { describe, expect, it, vi } from "vitest";

import { projectTypeDependencies, resolveCascade, typeModuleName } from "../cascade";
import { makeType, projectType } from "./fixtures";

const spectrum = projectType("Spectrum", "spectrum");
const trace = projectType("Trace", "trace");
const coreArray = makeType({ name: "Array", origin: "core" });
const userType = makeType({
  name: "MyDenoised",
  origin: "user",
  file_path: "/home/dev/.scistudio/types/my_denoised.py",
});
const packaged = makeType({
  name: "Cube",
  origin: "package",
  file_path: "/site-packages/imaging/types/cube.py",
});

describe("typeModuleName", () => {
  it("is the file stem a drop-in is importable by", () => {
    expect(typeModuleName(spectrum)).toBe("spectrum");
  });

  it("is null when the type has no resolvable file", () => {
    expect(typeModuleName(makeType({ name: "Nowhere" }))).toBeNull();
  });
});

describe("projectTypeDependencies — FR-021 / FR-022", () => {
  const catalogue = [spectrum, trace, coreArray, userType, packaged];

  it("finds a project type imported by its module stem", () => {
    const found = projectTypeDependencies("from spectrum import Spectrum\n", catalogue);
    expect(found.map((entry) => entry.type.name)).toEqual(["Spectrum"]);
  });

  it("finds a project type imported by its registered name", () => {
    // `types/my_types.py` declaring `Trace` — the stem does not match, the
    // bound name does.
    const renamed = projectType("Trace", "my_types");
    const found = projectTypeDependencies("from my_types import Trace\n", [renamed]);
    expect(found.map((entry) => entry.type.name)).toEqual(["Trace"]);
  });

  it("classifies by origin: core, user, and packaged types are never dependencies", () => {
    const found = projectTypeDependencies(
      "import array\nfrom my_denoised import MyDenoised\nfrom cube import Cube\n",
      catalogue,
    );
    expect(found).toEqual([]);
  });

  it("finds several dependencies, ordered by name", () => {
    const found = projectTypeDependencies("import trace\nimport spectrum\n", catalogue);
    expect(found.map((entry) => entry.type.name)).toEqual(["Spectrum", "Trace"]);
  });

  it("finds nothing when the block imports nothing project-local", () => {
    expect(projectTypeDependencies("import numpy as np\n", catalogue)).toEqual([]);
  });
});

describe("resolveCascade — FR-023 / FR-024", () => {
  const catalogue = [spectrum, trace, coreArray];

  it("reports a second-level dependency rather than promoting or dropping it", async () => {
    // The block imports Spectrum; Spectrum itself imports Trace. FR-024 keeps
    // the cascade one level deep, so Trace is reported, never silently missed.
    const read = vi.fn(async () => "from trace import Trace\n");
    const plan = await resolveCascade("from spectrum import Spectrum\n", catalogue, read);

    expect(plan.dependencies.map((entry) => entry.type.name)).toEqual(["Spectrum"]);
    expect(plan.secondLevel).toEqual([{ type: trace, via: spectrum }]);
    expect(plan.unreadable).toEqual([]);
  });

  it("does not re-report a type that is already a first-level dependency", async () => {
    const read = vi.fn(async () => "from trace import Trace\n");
    const plan = await resolveCascade("import spectrum\nimport trace\n", catalogue, read);
    expect(plan.dependencies.map((entry) => entry.type.name)).toEqual(["Spectrum", "Trace"]);
    expect(plan.secondLevel).toEqual([]);
  });

  it("reports a dependency whose own source could not be read", async () => {
    const read = vi.fn(async () => {
      throw new Error("nope");
    });
    const plan = await resolveCascade("import spectrum\n", catalogue, read);
    expect(plan.dependencies.map((entry) => entry.type.name)).toEqual(["Spectrum"]);
    expect(plan.unreadable).toEqual([spectrum]);
  });

  it("never walks past the second level", async () => {
    // Spectrum → Trace → (whatever Trace imports) must not be followed.
    const read = vi.fn(async () => "from trace import Trace\n");
    await resolveCascade("import spectrum\n", catalogue, read);
    expect(read).toHaveBeenCalledTimes(1);
  });
});
