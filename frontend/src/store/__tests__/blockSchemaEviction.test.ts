// #1988 — the block catalog is the authority on which block types exist.
//
// `setBlockSchema` only merges, so before this the schema map grew
// monotonically: deleting a drop-in block and reloading the catalog left its
// schema behind forever. Anything asking "did this block type resolve?" would
// still find a schema and draw the node as a working block — stale ports, no
// warning — which is precisely the state #1988 exists to surface.

import { describe, expect, it } from "vitest";

import { useAppStore } from "../index";
import type { BlockSchemaResponse, BlockSummary } from "../../types/api";

function summary(type_name: string): BlockSummary {
  return {
    name: type_name,
    type_name,
    base_category: "process",
    input_ports: [],
    output_ports: [],
  } as unknown as BlockSummary;
}

function schema(type_name: string): BlockSchemaResponse {
  return {
    name: type_name,
    type_name,
    input_ports: [],
    output_ports: [],
  } as unknown as BlockSchemaResponse;
}

describe("#1988 block schema cache eviction", () => {
  it("drops schemas for types the refreshed catalog no longer contains", () => {
    const store = useAppStore.getState();
    store.setBlocks([summary("keeper_block"), summary("doomed_block")]);
    store.setBlockSchema(schema("keeper_block"));
    store.setBlockSchema(schema("doomed_block"));
    expect(Object.keys(useAppStore.getState().blockSchemas).sort()).toEqual([
      "doomed_block",
      "keeper_block",
    ]);

    // The drop-in file was deleted and the catalog reloaded without it.
    useAppStore.getState().setBlocks([summary("keeper_block")]);

    const after = useAppStore.getState().blockSchemas;
    expect(Object.keys(after)).toEqual(["keeper_block"]);
    expect(after.doomed_block).toBeUndefined();
  });

  it("keeps schemas for types still in the catalog", () => {
    const store = useAppStore.getState();
    store.setBlocks([summary("a_block"), summary("b_block")]);
    store.setBlockSchema(schema("a_block"));
    store.setBlockSchema(schema("b_block"));

    useAppStore.getState().setBlocks([summary("b_block"), summary("a_block")]);

    expect(Object.keys(useAppStore.getState().blockSchemas).sort()).toEqual(["a_block", "b_block"]);
  });

  it("does not prune on an empty catalog", () => {
    // `setBlocks([])` happens while a project loads and between projects.
    // Pruning there would throw away schemas the next render needs.
    const store = useAppStore.getState();
    store.setBlocks([summary("live_block")]);
    store.setBlockSchema(schema("live_block"));

    useAppStore.getState().setBlocks([]);

    expect(useAppStore.getState().blocks).toEqual([]);
    expect(useAppStore.getState().blockSchemas.live_block).toBeDefined();
  });
});
