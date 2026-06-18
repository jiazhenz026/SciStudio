/**
 * MiniMap wrapper for WorkflowCanvas — uses resolveTypeColor to colour
 * dots by primary output type. Extracted in #1413.
 */
import { MiniMap } from "@xyflow/react";

import { resolveTypeColor } from "../../config/typeColorMap";
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
        if (node.type === "_annotation" || node.type === "_group") {
          return dimmed ? "#ece9e3" : "#d6d3d1";
        }
        if (dimmed) return "#e2ded7";
        const data = node.data as BlockNodeData | undefined;
        const color = resolveTypeColor(data?.outputPorts?.[0]?.accepted_types ?? []);
        // Fallback DataObject gray (#e5e7eb) is nearly invisible on the
        // light minimap background — use a darker substitute.
        return color === "#e5e7eb" ? "#9ca3af" : color;
      }}
    />
  );
}
