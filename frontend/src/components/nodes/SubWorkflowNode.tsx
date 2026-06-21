// SubWorkflowNode — ADR-044 §3 authoring-only container glyph.
//
// A `subworkflow` node references an external workflow file (`config.ref.path`)
// and exposes that file's `exposed_ports` as React Flow handles so the parent
// canvas can connect to the sub-pipeline as if it were a single block. The
// node has NO run()-time behaviour: by the time the scheduler runs, the parser
// has inline-flattened it away (ADR-044 §4) — the editor only ever sees the
// authored container.
//
// Rendering rules:
//   - Reuse the fixed 104×104 square topology + label-below pattern from
//     BlockNode and the subworkflow category visual (Package icon, pink) from
//     `getCategoryVisual("subworkflow")`.
//   - Ports are derived from the referenced file's `exposed_ports`
//     (response-only `resolved_ports`), so they are NOT user-editable here:
//     `PortHandles` runs with `isVariadicInputs/Outputs={false}` and
//     `canAdd/canRemove={false}`. Handle ids equal the exposed port names so
//     existing colon-ref edge connect/persist logic works unchanged
//     (ADR-044 locked contract item 4).
//   - Broken state (`subworkflow_broken` / unresolved ref): red placeholder
//     with a clear "broken reference" label showing the unresolved `ref_path`
//     and a "locate file…" affordance (ADR-044 §10 / spec US 6).
//
// Double-click → open the referenced file in a canvas tab is wired at the
// canvas level (`onNodeDoubleClick` in WorkflowCanvas), not here.

import { type Node, type NodeProps } from "@xyflow/react";

import type { BlockNodeData, SubWorkflowNodeData } from "../../types/ui";

import { PortHandles } from "./BlockNode.parts/PortHandles";
import { getCategoryVisual } from "./BlockNode.parts/categoryVisuals";
import { NODE_BORDER_RADIUS, NODE_SIZE } from "./BlockNode.parts/nodeGeometry";

/** Broken-ref placeholder palette (ADR-044 §10 — red, distinct from the
 *  healthy pink subworkflow macaron). */
const BROKEN_VISUAL = {
  bg: "#fde2e2",
  fg: "#b91c1c",
  border: "#f3a3a3",
} as const;

export function SubWorkflowNode({ id, data, selected }: NodeProps<Node<SubWorkflowNodeData>>) {
  const visual = getCategoryVisual("subworkflow");
  const CategoryIcon = visual.Icon;
  const broken = data.broken;

  const bg = broken ? BROKEN_VISUAL.bg : visual.bg;
  const fg = broken ? BROKEN_VISUAL.fg : visual.fg;
  const border = broken ? BROKEN_VISUAL.border : visual.border;

  // PortHandles is BlockNode-shaped; bridge the subworkflow data onto the
  // BlockNodeData fields it reads (schema/config) without making the ports
  // user-editable. Ports come from the referenced file, never from edits, so
  // every variadic + add/remove affordance is disabled (ADR-044 §3).
  const portHandlesData: BlockNodeData = {
    label: data.label,
    blockType: data.blockType,
    category: "subworkflow",
    inputPorts: data.inputPorts,
    outputPorts: data.outputPorts,
    schema: data.typeHierarchy
      ? // PortHandles only reads `schema.type_hierarchy` for port colours and
        // `schema.allowed_*_types` (variadic dialog, never opened here). A
        // minimal shim avoids forcing a full BlockSchemaResponse on the wire.
        ({ type_hierarchy: data.typeHierarchy } as BlockNodeData["schema"])
      : undefined,
    config: {},
  };

  return (
    <div data-testid="subworkflow-node-shell" className="relative">
      <div
        data-testid="subworkflow-node-body"
        data-broken={broken ? "true" : "false"}
        className={`relative flex items-center justify-center border shadow-sm ${
          selected ? "border-ember shadow-panel" : ""
        }`}
        style={{
          width: NODE_SIZE,
          height: NODE_SIZE,
          borderRadius: NODE_BORDER_RADIUS,
          backgroundColor: bg,
          borderColor: selected ? undefined : border,
        }}
      >
        <CategoryIcon
          data-testid="subworkflow-node-icon"
          size={48}
          color={fg}
          strokeWidth={1.75}
          aria-hidden="true"
        />

        {/* Healthy refs render exposed-port handles; broken refs have none
            (resolved_ports.inputs/outputs are empty per the locked contract). */}
        <PortHandles
          nodeId={id}
          data={portHandlesData}
          effectiveInputPorts={data.inputPorts}
          effectiveOutputPorts={data.outputPorts}
          isVariadicInputs={false}
          isVariadicOutputs={false}
          canAddInput={false}
          canRemoveInput={false}
          canAddOutput={false}
          canRemoveOutput={false}
        />
      </div>

      {broken ? (
        <BrokenRefBanner refPath={data.refPath} onLocateFile={data.onLocateFile} />
      ) : (
        <span
          data-testid="subworkflow-node-label"
          className="pointer-events-none absolute left-1/2 top-full mt-1.5 line-clamp-2 w-[140px] -translate-x-1/2 text-center font-display text-[13px] font-semibold leading-tight text-ink"
          title={data.refPath ?? data.label}
        >
          {data.label}
        </span>
      )}
    </div>
  );
}

/** ADR-044 §10 / FR-011 / spec US 5 + US 6 — broken / no-ref banner + the
 *  shared choose-or-locate affordance shown below a red placeholder node.
 *
 *  A node with NO ref (freshly dropped `subworkflow_block`) shows "Choose
 *  subworkflow file…"; a node whose ref is broken (the file moved / was
 *  deleted) shows "Locate file…". Both run the SAME shared flow
 *  (`chooseSubworkflowFile` via `onLocateFile`); the only difference is the
 *  label and the explanatory copy. */
function BrokenRefBanner({
  refPath,
  onLocateFile,
}: {
  refPath: string | null;
  onLocateFile?: () => void;
}) {
  const hasRef = Boolean(refPath);
  const heading = hasRef ? "Broken reference" : "No subworkflow file";
  const buttonLabel = hasRef ? "Locate file…" : "Choose subworkflow file…";
  return (
    <div
      data-testid="subworkflow-node-broken"
      className="absolute left-1/2 top-full mt-1.5 flex w-[160px] -translate-x-1/2 flex-col items-center gap-1 text-center"
    >
      <span className="font-display text-[12px] font-semibold leading-tight text-red-700">
        {heading}
      </span>
      <span
        data-testid="subworkflow-node-broken-path"
        className="line-clamp-2 break-all text-[10px] leading-tight text-red-600"
        title={refPath ?? "(no path)"}
      >
        {refPath ?? "(no path)"}
      </span>
      {onLocateFile ? (
        <button
          type="button"
          data-testid="subworkflow-node-locate"
          className="nodrag rounded border border-red-300 bg-red-50 px-2 py-0.5 text-[10px] font-medium text-red-700 transition-colors hover:bg-red-100"
          onClick={(event) => {
            event.stopPropagation();
            onLocateFile();
          }}
        >
          {buttonLabel}
        </button>
      ) : null}
    </div>
  );
}
