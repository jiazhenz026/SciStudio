/**
 * MiniMap wrapper for WorkflowCanvas. Live hotfix batch: minimap dots now use
 * each block's body fill (its base-category macaron colour) so the map matches
 * the canvas at a glance, instead of colouring by primary output type.
 */
import { MiniMap } from "@xyflow/react";

import { getCategoryVisual } from "../nodes/BlockNode.parts/categoryVisuals";
import type { BlockNodeData } from "../../types/ui";

export function WorkflowMiniMap() {
  return (
    <MiniMap
      pannable
      zoomable
      maskColor="rgba(245, 241, 232, 0.7)"
      style={{ backgroundColor: "#faf8f4" }}
      nodeColor={(node) => {
        // ADR-050 §3.1 — fade out-of-focus nodes on the minimap so the focused
        // subgraph reads clearly. WorkflowCanvas tags dimmed nodes with the
        // ``scistudio-focus-dimmed`` class during focus post-processing.
        const dimmed =
          typeof node.className === "string" && node.className.includes("scistudio-focus-dimmed");
        if (node.type === "_annotation") {
          return dimmed ? "#ece9e3" : "#d6d3d1";
        }
        if (dimmed) return "#e2ded7";
        const data = node.data as BlockNodeData | undefined;
        // Match the canvas: minimap dot = block body fill for its base category.
        return getCategoryVisual(data?.category).bg;
      }}
    />
  );
}
