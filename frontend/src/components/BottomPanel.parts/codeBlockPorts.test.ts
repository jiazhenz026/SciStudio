import { describe, expect, it } from "vitest";

import {
  codeBlockFolder,
  isCodeBlockConfigTarget,
  isRecord,
  nextCodeBlockPortName,
  normalizeCodeBlockPort,
  persistCodeBlockPort,
} from "./codeBlockPorts";
import type { BlockSchemaResponse, WorkflowNode } from "../../types/api";

describe("codeBlockPorts helpers", () => {
  describe("isRecord", () => {
    it("returns true for plain objects", () => {
      expect(isRecord({ a: 1 })).toBe(true);
    });
    it("returns false for null, arrays, primitives", () => {
      expect(isRecord(null)).toBe(false);
      expect(isRecord([])).toBe(false);
      expect(isRecord("string")).toBe(false);
      expect(isRecord(42)).toBe(false);
    });
  });

  describe("isCodeBlockConfigTarget", () => {
    it("detects code_block schemas via type_name", () => {
      const schema = { type_name: "code_block" } as BlockSchemaResponse;
      expect(isCodeBlockConfigTarget(null, schema)).toBe(true);
    });
    it("detects via block_type on node", () => {
      const node = { id: "n", block_type: "CodeBlock", config: { params: {} } } as WorkflowNode;
      expect(isCodeBlockConfigTarget(node)).toBe(true);
    });
    it("matches tokens ending in 'codeblock'", () => {
      const schema = { type_name: "my-code-block" } as BlockSchemaResponse;
      expect(isCodeBlockConfigTarget(null, schema)).toBe(true);
    });
    it("returns false for non-code-block schemas", () => {
      const schema = { type_name: "process_block" } as BlockSchemaResponse;
      expect(isCodeBlockConfigTarget(null, schema)).toBe(false);
    });
  });

  describe("codeBlockFolder", () => {
    it("produces inputs/<name>/ for input direction", () => {
      expect(codeBlockFolder("input", "foo")).toBe("inputs/foo/");
    });
    it("produces outputs/<name>/ for output direction", () => {
      expect(codeBlockFolder("output", "bar")).toBe("outputs/bar/");
    });
    it("defaults blank names to 'port'", () => {
      expect(codeBlockFolder("input", "")).toBe("inputs/port/");
      expect(codeBlockFolder("input", "   ")).toBe("inputs/port/");
    });
  });

  describe("nextCodeBlockPortName", () => {
    it("returns input_1 when no ports", () => {
      expect(nextCodeBlockPortName("input", [])).toBe("input_1");
    });
    it("avoids collisions with existing ports", () => {
      const ports = [
        {
          name: "input_1",
          direction: "input" as const,
          data_type: "DataObject",
          extension: ".txt",
          required: true,
          exchange_folder: "inputs/input_1/",
        },
      ];
      expect(nextCodeBlockPortName("input", ports)).toBe("input_2");
    });
  });

  describe("normalizeCodeBlockPort", () => {
    it("fills sensible defaults from empty input", () => {
      const port = normalizeCodeBlockPort({}, "input", 0);
      expect(port.name).toBe("input_1");
      expect(port.data_type).toBe("DataObject");
      expect(port.extension).toBe(".txt");
      expect(port.required).toBe(true);
      expect(port.exchange_folder).toBe("inputs/input_1/");
    });
    it("uses provided values when present", () => {
      const port = normalizeCodeBlockPort(
        { name: "image", data_type: "Image", extension: ".tif", required: false },
        "input",
        0,
      );
      expect(port.name).toBe("image");
      expect(port.data_type).toBe("Image");
      expect(port.extension).toBe(".tif");
      expect(port.required).toBe(false);
    });
    it("treats non-record value as empty row", () => {
      const port = normalizeCodeBlockPort("not-a-record", "output", 2);
      expect(port.name).toBe("output_3");
    });
  });

  describe("persistCodeBlockPort", () => {
    it("trims fields and falls back to default exchange folder", () => {
      const persisted = persistCodeBlockPort(
        {
          name: "  foo  ",
          direction: "input",
          data_type: " Array ",
          extension: " .csv ",
          capability_id: "  ",
          required: true,
          exchange_folder: " ",
        },
        "input",
      );
      expect(persisted.name).toBe("foo");
      expect(persisted.data_type).toBe("Array");
      expect(persisted.extension).toBe(".csv");
      expect(persisted.capability_id).toBeNull();
      expect(persisted.exchange_folder).toBe("inputs/foo/");
    });
  });
});
