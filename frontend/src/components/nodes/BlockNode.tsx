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
import { useEffect, useRef, useState } from "react";

import type { BlockNodeData } from "../../types/ui";
import { computeEffectivePorts } from "../../utils/computeEffectivePorts";

import { BlockDetailPopover, type PopoverAnchor } from "../BlockDetailPopover";
import { NodeActionToolbar } from "./BlockNode.parts/NodeActionToolbar";
import { NodeStatusSurface } from "./BlockNode.parts/NodeStatusSurface";
import { PortHandles } from "./BlockNode.parts/PortHandles";
import { getCategoryVisual } from "./BlockNode.parts/categoryVisuals";
import { NODE_BORDER_RADIUS, NODE_SIZE } from "./BlockNode.parts/nodeGeometry";
import {
  NODE_DETAIL_OPEN_DELAY_MS,
  computeNodeDetailAnchor,
} from "./BlockNode.parts/nodeDetailAnchor";

export function BlockNode({ id: nodeId, data, selected }: NodeProps<Node<BlockNodeData>>) {
  // ADR-050 §2.1 — block-kind mark + macaron body colour from the base
  // category (lucide line icon), with optional per-block overrides (#1839):
  // a block may declare its own `ui_color` / `ui_icon` on its summary, which
  // take precedence over the category default (unknown icon name falls back).
  const visual = getCategoryVisual(data.category, data.summary?.ui_color, data.summary?.ui_icon);
  const CategoryIcon = visual.Icon;

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
  //
  // The toolbar floats ABOVE the square with a small gap; moving the cursor
  // from the node up to the toolbar briefly crosses that gap (leaving the
  // shell's bounds), which would hide the toolbar before it can be clicked.
  // A short hide DELAY (cancelled on re-enter, including re-enter onto the
  // toolbar itself, which is a shell descendant) lets the user reach it
  // without first selecting the node (#1698 canvas UX).
  const [hovered, setHovered] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // #1887 — hover detail popover. Mirrors the palette's hover detail but for a
  // placed node: after a short dwell, show the shared BlockDetailPopover with
  // this block's summary, anchored beside the node's on-screen rect (so it is
  // correct under any canvas zoom/pan). It floats to the side of the square and
  // is pointer-events-none, so it never collides with the action toolbar that
  // floats above. No-op when the block summary is unavailable (e.g. an
  // unresolved custom/plugin block).
  const shellRef = useRef<HTMLDivElement>(null);
  const [detailAnchor, setDetailAnchor] = useState<PopoverAnchor | null>(null);
  const detailTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const summary = data.summary;

  const showActions = () => {
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    setHovered(true);
    if (summary && typeof window !== "undefined") {
      if (detailTimer.current) clearTimeout(detailTimer.current);
      detailTimer.current = setTimeout(() => {
        const rect = shellRef.current?.getBoundingClientRect();
        if (!rect) return;
        setDetailAnchor(
          computeNodeDetailAnchor(rect, {
            width: window.innerWidth,
            height: window.innerHeight,
          }),
        );
        detailTimer.current = null;
      }, NODE_DETAIL_OPEN_DELAY_MS);
    }
  };
  const scheduleHideActions = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      setHovered(false);
      hideTimer.current = null;
    }, 450);
    // The detail popover sits beside the node and has no controls to reach, so
    // it dismisses immediately on leave rather than after the toolbar delay.
    if (detailTimer.current) {
      clearTimeout(detailTimer.current);
      detailTimer.current = null;
    }
    setDetailAnchor(null);
  };
  useEffect(
    () => () => {
      if (hideTimer.current) clearTimeout(hideTimer.current);
      if (detailTimer.current) clearTimeout(detailTimer.current);
    },
    [],
  );
  const actionsVisible = hovered || selected === true;

  return (
    <div
      ref={shellRef}
      data-testid="block-node-shell"
      className="relative"
      onMouseEnter={showActions}
      onMouseLeave={scheduleHideActions}
    >
      {/* Floating actions — outside the square body (ADR-050 §2.2). */}
      <NodeActionToolbar
        visible={actionsVisible}
        onRun={data.onRun}
        onRestart={data.onRestart}
        onDelete={data.onDelete}
      />

      {/* Hover detail popover beside the node (#1887). Shared with the palette;
          pointer-events-none + fixed positioning keep it out of layout flow. */}
      {detailAnchor && summary ? (
        <BlockDetailPopover anchor={detailAnchor} block={summary} />
      ) : null}

      {/* ----------------------------------------------------------------- */}
      {/* Fixed 104×104 square body — identity only (ADR-050 §2.1)          */}
      {/* Width === height and never grows; status/actions/ports overlay    */}
      {/* via absolute positioning and do not change measured geometry.     */}
      {/* ----------------------------------------------------------------- */}
      <div
        data-testid="block-node-body"
        className={`relative flex items-center justify-center border shadow-sm ${
          selected ? "border-ember shadow-panel" : ""
        } ${
          // #1799 — plot picker highlight: a ring that reads as "this is the
          // block that target row points at", without the selection semantics.
          data.highlighted ? "ring-2 ring-ember ring-offset-2 ring-offset-canvas" : ""
        }`}
        style={{
          width: NODE_SIZE,
          height: NODE_SIZE,
          borderRadius: NODE_BORDER_RADIUS,
          backgroundColor: visual.bg,
          borderColor: selected ? undefined : visual.border,
        }}
      >
        {/* Block-kind mark — single lucide line icon in the category accent
            colour (n8n-style glyph; the body shows identity, nothing else). */}
        <CategoryIcon
          data-testid="block-node-category-icon"
          size={48}
          color={visual.fg}
          strokeWidth={1.75}
          aria-hidden="true"
        />

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

      {/* Block label BELOW the square (n8n-style): the body stays a pure
          glyph and the name reads underneath, where it may be a little wider
          than the square. Absolute + `top-full` keeps it out of layout flow
          (zero geometry impact); two-line clamp + ellipsis bound long names,
          full text in the title tooltip. */}
      <span
        data-testid="block-node-label"
        className="pointer-events-none absolute left-1/2 top-full mt-1.5 line-clamp-2 w-[140px] -translate-x-1/2 text-center font-display text-[13px] font-semibold leading-tight text-ink"
        title={data.label}
      >
        {data.label}
      </span>
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
