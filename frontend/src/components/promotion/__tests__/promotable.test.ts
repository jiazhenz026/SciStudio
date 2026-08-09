// ADR-053 FR-019 — what may be promoted, and how each entry point resolves it.

import { describe, expect, it } from "vitest";

import type { FileTab } from "../../../store/types";
import { isPromotable, promotableBlock, promotableFileTab, promotableType } from "../promotable";
import { makeBlock, makeType } from "./fixtures";

function fileTab(overrides: Partial<FileTab> & { filePath: string }): FileTab {
  return {
    kind: "file",
    id: `file:${overrides.filePath}`,
    filePath: overrides.filePath,
    displayName: overrides.filePath,
    language: "python",
    content: overrides.content ?? "",
    contentLoadedAt: 0,
    dirty: false,
    readOnly: overrides.readOnly ?? false,
    blockSourceType: overrides.blockSourceType,
  };
}

describe("isPromotable — FR-019 the condition is the resolved origin", () => {
  it("accepts a project-tier block", () => {
    expect(
      isPromotable(promotableBlock(makeBlock({ type_name: "n", name: "N", origin: "project" }))),
    ).toBe(true);
  });

  it.each(["builtin", "package", "user", "custom"] as const)(
    "refuses a %s block — it is already in a library or unresolvable",
    (origin) => {
      const block = makeBlock({ type_name: "n", name: "N", origin });
      expect(isPromotable(promotableBlock(block))).toBe(false);
    },
  );

  it("refuses a user-library block even though it is tier-1 with a file path", () => {
    // Spec §6: the broader "is it tier-1" test would offer promotion for an
    // item that is already promoted.
    const promoted = makeBlock({ type_name: "n", name: "N", origin: "user", source: "custom" });
    expect(isPromotable(promotableBlock(promoted))).toBe(false);
  });

  it.each(["core", "package", "user", "custom"] as const)("refuses a %s type", (origin) => {
    const type = makeType({ name: "T", origin, file_path: "/somewhere/t.py" });
    expect(isPromotable(promotableType(type))).toBe(false);
  });

  it("refuses null (nothing resolvable on the surface)", () => {
    expect(isPromotable(null)).toBe(false);
  });
});

describe("promotableType", () => {
  it("targets the types library and reads the project types directory", () => {
    const type = makeType({
      name: "Spectrum",
      origin: "project",
      file_path: "/home/dev/proj/types/spectrum.py",
    });
    expect(promotableType(type)).toEqual({
      target: "types",
      kind: "type",
      label: "Spectrum",
      origin: "project",
      source: { from: "projectFile", path: "types/spectrum.py" },
    });
  });

  it("is null for a type with no resolvable file", () => {
    expect(promotableType(makeType({ name: "T", origin: "project" }))).toBeNull();
  });
});

describe("promotableFileTab — entry point E1", () => {
  const blocks = [
    makeBlock({ type_name: "normalize", name: "Normalize", origin: "project" }),
    makeBlock({ type_name: "load_data", name: "Load", origin: "builtin" }),
  ];

  it("resolves a block-source tab through the registered summary", () => {
    const tab = fileTab({ filePath: "/proj/blocks/normalize.py", blockSourceType: "normalize" });
    expect(promotableFileTab(tab, blocks)).toEqual({
      target: "blocks",
      kind: "block",
      label: "Normalize",
      origin: "project",
      source: { from: "block", blockType: "normalize" },
    });
  });

  it("keeps a built-in block-source tab unpromotable", () => {
    const tab = fileTab({ filePath: "/site/load_data.py", blockSourceType: "load_data" });
    expect(isPromotable(promotableFileTab(tab, blocks))).toBe(false);
  });

  it("resolves an edited project drop-in block file as project-tier", () => {
    expect(promotableFileTab(fileTab({ filePath: "blocks/my_block.py" }), blocks)).toEqual({
      target: "blocks",
      kind: "block",
      label: "my_block",
      origin: "project",
      source: { from: "projectFile", path: "blocks/my_block.py" },
    });
  });

  it("resolves an edited project drop-in type file to the types target", () => {
    expect(promotableFileTab(fileTab({ filePath: "types/spectrum.py" }), blocks)).toEqual({
      target: "types",
      kind: "type",
      label: "spectrum",
      origin: "project",
      source: { from: "projectFile", path: "types/spectrum.py" },
    });
  });

  it("refuses a nested file that no drop-in scan would pick up", () => {
    expect(promotableFileTab(fileTab({ filePath: "blocks/vendor/x.py" }), blocks)).toBeNull();
  });

  it("refuses a non-Python file and a non-drop-in directory", () => {
    expect(promotableFileTab(fileTab({ filePath: "notes/todo.md" }), blocks)).toBeNull();
    expect(promotableFileTab(fileTab({ filePath: "scripts/run.py" }), blocks)).toBeNull();
  });

  it("refuses when no tab is open", () => {
    expect(promotableFileTab(null, blocks)).toBeNull();
  });
});
