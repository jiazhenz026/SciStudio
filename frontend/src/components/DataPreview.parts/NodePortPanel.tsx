// NodePortPanel — the right-pane port section for the selected node.
//
// Extracted from DataPreview to keep that component under the complexity cap:
// it owns the branch between the ADR-044 subworkflow provenance panel (when the
// selected node is a subworkflow container) and the #1326 generic PortInfoPanel
// (every other block), plus the shared scroll wrapper. Renders null when there
// is nothing to show so DataPreview can drop it without an empty container.

import type {
  BlockPortResponse,
  BlockSchemaResponse,
  ResolvedSubworkflowPort,
} from "../../types/api";

import { PortInfoPanel } from "./PortInfoPanel";
import { SubworkflowPortPanel } from "./SubworkflowPortPanel";

interface NodePortPanelProps {
  /** ADR-044 — exposed-port surface when the selected node is a subworkflow. */
  subworkflowPorts?: {
    inputs: ResolvedSubworkflowPort[];
    outputs: ResolvedSubworkflowPort[];
    typeHierarchy?: BlockSchemaResponse["type_hierarchy"];
  };
  inputPorts: BlockPortResponse[];
  outputPorts: BlockPortResponse[];
  schema?: BlockSchemaResponse;
}

export function NodePortPanel({
  subworkflowPorts,
  inputPorts,
  outputPorts,
  schema,
}: NodePortPanelProps) {
  const hasSubworkflowPorts =
    (subworkflowPorts?.inputs.length ?? 0) > 0 || (subworkflowPorts?.outputs.length ?? 0) > 0;
  const hasGenericPorts = inputPorts.length > 0 || outputPorts.length > 0;
  if (!hasSubworkflowPorts && !hasGenericPorts) return null;

  return (
    <div className="flex shrink-0 basis-[38%] flex-col overflow-y-auto scrollbar-thin">
      {hasSubworkflowPorts ? (
        <SubworkflowPortPanel
          inputs={subworkflowPorts?.inputs ?? []}
          outputs={subworkflowPorts?.outputs ?? []}
          typeHierarchy={subworkflowPorts?.typeHierarchy}
        />
      ) : (
        <PortInfoPanel inputPorts={inputPorts} outputPorts={outputPorts} schema={schema} />
      )}
    </div>
  );
}
