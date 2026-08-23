import type { StateCreator } from "zustand";

import type { AppStore, PaletteSlice } from "./types";

export const createPaletteSlice: StateCreator<AppStore, [], [], PaletteSlice> = (set) => ({
  blocks: [],
  blockSchemas: {},
  paletteSearch: "",
  // #1988 — the block catalog is the authority on which block types exist, so
  // replacing it must also evict schemas for types it no longer contains.
  // `setBlockSchema` only ever merges, so without this the map grows
  // monotonically: delete a drop-in block and reload the catalog, and its stale
  // schema survives. Anything asking "did this type resolve?" would then still
  // see a schema and render the node as a working block — with stale ports and
  // no warning — which is exactly the state #1988 exists to make visible.
  //
  // Guarded on a non-empty catalog: `setBlocks([])` happens while a project is
  // loading or between projects, and pruning on that would throw away schemas
  // the very next render needs.
  setBlocks: (blocks) =>
    set((state) => {
      if (blocks.length === 0) return { blocks };
      const live = new Set(blocks.map((block) => block.type_name));
      const kept = Object.fromEntries(
        Object.entries(state.blockSchemas).filter(([typeName]) => live.has(typeName)),
      );
      return { blocks, blockSchemas: kept };
    }),
  setBlockSchema: (schema) =>
    set((state) => ({
      blockSchemas: {
        ...state.blockSchemas,
        [schema.type_name]: schema,
      },
    })),
  setPaletteSearch: (paletteSearch) => set({ paletteSearch }),
});
