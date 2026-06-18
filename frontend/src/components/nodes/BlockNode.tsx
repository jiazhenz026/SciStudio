// BlockNode — fixed square topology glyph for a SciStudio block instance.
//
// ADR-050 §2 rewrite (#1698): the canvas node is a fixed 104×104 square whose
// body shows block IDENTITY ONLY — the block-kind category mark and the block
// label (capped to two visual lines). Computational configuration moved
// entirely to the BottomPanel Config tab; the node body renders NO config
// fields, NO data-type/role subtitle, NO status footer, NO inline error text,
// NO warning chip, and NO paused toast. The body never grows for any reason
// (FR-001..FR-007, FR-011).
//
// Runtime state, warnings, and errors render through the single unified
// `NodeStatusSurface` corner glyph. Run/restart/delete float OUTSIDE the
// square in `NodeActionToolbar` on hover/selected. Port handles + ADR-029
// variadic +/- controls stay on the left/right rails via `PortHandles`,
// aligned to the square through `nodeGeometry`.
//
// This module owns the per-instance computations that drive the sub-modules
// (effective ports for dynamic blocks, variadic min/max limits) — the same
// contracts as before, minus the deleted inline-config path.

import { type Node, type NodeProps } from "@xyflow/react";
import { useState } from "react";

import type { BlockNodeData } from "../../types/ui";
import { computeEffectivePorts } from "../../utils/computeEffectivePorts";

import { NodeActionToolbar } from "./BlockNode.parts/NodeActionToolbar";
import { NodeStatusSurface } from "./BlockNode.parts/NodeStatusSurface";
import { PortHandles } from "./BlockNode.parts/PortHandles";
import { categoryIcons } from "./BlockNode.parts/badgeStyles";
import { NODE_BORDER_RADIUS, NODE_SIZE } from "./BlockNode.parts/nodeGeometry";

export function BlockNode({ id: nodeId, data, selected }: NodeProps<Node<BlockNodeData>>) {
  // ADR-050 §2.1 — block-kind mark from the package-provided category.
  const categoryIcon = categoryIcons[data.category] ?? categoryIcons.custom;

  // ADR-028 Addendum 1 §D4 — compute effective ports from the dynamic-port
  // descriptor + driving config value so dynamic blocks (LoadData / SaveData)
  // get per-instance accepted_types and correct port colours. Static blocks
  // pay zero cost (the helper returns basePorts by reference). The driving
  // config value is read directly from `data.config`; the node body no longer
  // renders an editor for it (config lives in BottomPanel), but the value the
  // user picked there still drives the port type shown on the canvas.
  const dynamicPorts = data.schema?.dynamic_ports ?? null;
  const sourceConfigKey = dynamicPorts?.source_config_key;
  const drivingConfigValue = resolveDrivingConfigValue(data, sourceConfigKey);
  const effectiveInputPorts = computeEffectivePorts(
    dynamicPorts,
    drivingConfigValue,
    data.inputPorts,
    "input",
  );
  const effectiveOutputPorts = computeEffectivePorts(
    dynamicPorts,
    drivingConfigValue,
    data.outputPorts,
    "output",
  );

  // ADR-029 D2 / Addendum 1 — variadic port UI: [+] / [-] controls + min/max.
  const isVariadicInputs = data.schema?.variadic_inputs === true;
  const isVariadicOutputs = data.schema?.variadic_outputs === true;
  const minInputPorts = data.schema?.min_input_ports ?? null;
  const maxInputPorts = data.schema?.max_input_ports ?? null;
  const minOutputPorts = data.schema?.min_output_ports ?? null;
  const maxOutputPorts = data.schema?.max_output_ports ?? null;
  const canAddInput = maxInputPorts == null || effectiveInputPorts.length < maxInputPorts;
  const canRemoveInput = minInputPorts == null || effectiveInputPorts.length > minInputPorts;
  const canAddOutput = maxOutputPorts == null || effectiveOutputPorts.length < maxOutputPorts;
  const canRemoveOutput = minOutputPorts == null || effectiveOutputPorts.length > minOutputPorts;

  // Action toolbar visibility is local hover state OR ReactFlow `selected`.
  // It is a floating overlay outside the square, so it never affects geometry.
  const [hovered, setHovered] = useState(false);
  const actionsVisible = hovered || selected === true;

  return (
    <div
      data-testid="block-node-shell"
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Floating actions — outside the square body (ADR-050 §2.2). */}
      <NodeActionToolbar
        visible={actionsVisible}
        onRun={data.onRun}
        onRestart={data.onRestart}
        onDelete={data.onDelete}
      />

      {/* ----------------------------------------------------------------- */}
      {/* Fixed 104×104 square body — identity only (ADR-050 §2.1)          */}
      {/* Width === height and never grows; status/actions/ports overlay    */}
      {/* via absolute positioning and do not change measured geometry.     */}
      {/* ----------------------------------------------------------------- */}
      <div
        data-testid="block-node-body"
        className={`relative flex flex-col items-center justify-center gap-1.5 border bg-white px-2 text-center shadow-sm ${
          selected ? "border-ember shadow-panel" : "border-stone-200"
        }`}
        style={{
          width: NODE_SIZE,
          height: NODE_SIZE,
          borderRadius: NODE_BORDER_RADIUS,
        }}
      >
        {/* Block-kind mark (category icon). */}
        <span className="text-2xl leading-none" aria-hidden="true">
          {categoryIcon}
        </span>

        {/* Block label — capped to two visual lines; overflow truncates with
            ellipsis and exposes the full text via the title tooltip. The
            `line-clamp-2` + fixed body height guarantee no geometry change. */}
        <span
          data-testid="block-node-label"
          className="line-clamp-2 w-full overflow-hidden font-display text-xs font-semibold leading-tight text-ink"
          title={data.label}
        >
          {data.label}
        </span>

        {/* Unified status surface — corner glyph, zero geometry impact. */}
        <NodeStatusSurface
          status={data.status}
          problemSeverity={data.problemSeverity}
          errorSummary={data.errorSummary}
          errorMessage={data.errorMessage}
          onErrorClick={data.onErrorClick}
          onWarningClick={data.onWarningClick}
        />

        {/* Port handles + variadic +/- controls on the left/right rails.
            Rendered inside the square body so ReactFlow positions handles
            relative to the node origin; rails may overflow below the square
            for many ports, but the body stays fixed (ADR-050 §2.4). */}
        <PortHandles
          nodeId={nodeId}
          data={data}
          effectiveInputPorts={effectiveInputPorts}
          effectiveOutputPorts={effectiveOutputPorts}
          isVariadicInputs={isVariadicInputs}
          isVariadicOutputs={isVariadicOutputs}
          canAddInput={canAddInput}
          canRemoveInput={canRemoveInput}
          canAddOutput={canAddOutput}
          canRemoveOutput={canRemoveOutput}
        />
      </div>
    </div>
  );
}

/**
 * Read the dynamic-port driving config value (e.g. LoadData `core_type`) from
 * the node config, falling back to the schema default. The user edits this in
 * BottomPanel Config; the node body only reads it to colour ports.
 */
function resolveDrivingConfigValue(
  data: BlockNodeData,
  sourceConfigKey: string | undefined,
): string | undefined {
  if (sourceConfigKey == null) return undefined;
  const configured = data.config?.[sourceConfigKey];
  if (typeof configured === "string" && configured) return configured;
  const properties = data.schema?.config_schema?.properties as
    | Record<string, Record<string, unknown>>
    | undefined;
  const schemaDefault = properties?.[sourceConfigKey]?.default;
  return typeof schemaDefault === "string" && schemaDefault ? schemaDefault : undefined;
}
