import { useEffect, useRef } from "react";

import { useAppStore } from "../store";

/**
 * Keep the block catalog (palette summaries + per-block schemas) in sync with
 * what the canvas actually renders, without a manual palette reload.
 *
 * - #2 / #8: reactive safety net. If a rendered workflow references a
 *   ``block_type`` not yet in the catalog (a project-scoped custom block, or a
 *   package block an agent added mid-session), the canvas node falls back to a
 *   generic, port-less "custom" placeholder. Re-fetch the catalog once per
 *   unseen type so the node resolves to its real IO/process styling + ports.
 *   The attempted-set guards against an infinite refresh loop for genuinely
 *   unregistered block types.
 * - #9: a ``blocks.reloaded`` WS event (the agent scaffolded + reloaded a
 *   custom block, or another client saved a block) bumps a store counter — this
 *   re-fetches the catalog so the palette + canvas pick up the change.
 */
export function useBlockCatalogSync(refreshBlocks: () => void | Promise<void>): void {
  const workflowNodes = useAppStore((state) => state.workflowNodes);
  const blocks = useAppStore((state) => state.blocks);
  const blockCatalogRefreshCounter = useAppStore((state) => state.blockCatalogRefreshCounter);

  const attemptedCatalogRefresh = useRef<Set<string>>(new Set());
  useEffect(() => {
    const known = new Set(blocks.map((block) => block.type_name));
    const missing = workflowNodes
      .map((node) => node.block_type)
      .filter(
        (type) =>
          Boolean(type) &&
          type !== "_annotation" &&
          type !== "_group" &&
          !known.has(type) &&
          !attemptedCatalogRefresh.current.has(type),
      );
    if (missing.length === 0) {
      return;
    }
    for (const type of missing) {
      attemptedCatalogRefresh.current.add(type);
    }
    void refreshBlocks();
  }, [workflowNodes, blocks, refreshBlocks]);

  useEffect(() => {
    if (blockCatalogRefreshCounter > 0) {
      void refreshBlocks();
    }
  }, [blockCatalogRefreshCounter, refreshBlocks]);
}
