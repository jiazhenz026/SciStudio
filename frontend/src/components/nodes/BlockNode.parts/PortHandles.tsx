// Extracted from BlockNode.tsx as part of the #1422 god-file split.
//
// PortHandles — renders the input + output ReactFlow `Handle`s for a block
// node along with the variadic add/remove controls. Behaviour preserved
// verbatim from the inline implementation:
//
//   - Each port is laid out by `portStartY + index * 20` so the first port
//     centers on the first inline-config row (#578 / ADR-028).
//   - Port colour is resolved from `accepted_types` + `typeHierarchy` via
//     the shared `resolveTypeColor` helpers; "Any"-typed ports get a
//     dashed grey ring.
//   - For variadic blocks (ADR-029 D2), a "+" button at the end of the
//     port column appends a new port and a per-port "×" button (revealed
//     on hover) removes one. min/max enforcement comes from the schema
//     fields read by the parent and passed through `canAddInput` etc.
//   - Removing a connected port prompts the user before the edges are
//     deleted via `useReactFlow().deleteElements`.

import type { Edge, HandleType } from "@xyflow/react";
import { Handle, Position, useEdges, useReactFlow } from "@xyflow/react";
import { useState } from "react";

import {
  isAnyType,
  primaryTypeName,
  resolveRingColor,
  resolveTypeColor,
} from "../../../config/typeColorMap";
import type { BlockPortResponse, BlockSchemaResponse } from "../../../types/api";
import type { BlockNodeData } from "../../../types/ui";

import { AddPortDialog } from "./AddPortDialog";

type Direction = "input" | "output";

interface PortStyle {
  fillColor: string;
  borderColor: string;
  anyType: boolean;
  typeName: string;
}

function computePortStyle(
  port: BlockPortResponse,
  typeHierarchy: BlockSchemaResponse["type_hierarchy"] | undefined,
): PortStyle {
  const fillColor = resolveTypeColor(port.accepted_types, typeHierarchy);
  const ringColor = resolveRingColor(port.accepted_types, typeHierarchy);
  const anyType = isAnyType(port.accepted_types);
  const typeName = primaryTypeName(port.accepted_types);
  const borderColor = ringColor ?? (anyType ? "#d1d5db" : fillColor);
  return { fillColor, borderColor, anyType, typeName };
}

interface PortRowProps {
  port: BlockPortResponse;
  index: number;
  portStartY: number;
  typeHierarchy: BlockSchemaResponse["type_hierarchy"] | undefined;
  direction: Direction;
  handleType: HandleType;
  position: Position;
  showRemoveButton: boolean;
  onRemove: (portName: string) => void;
}

function PortRow({
  port,
  index,
  portStartY,
  typeHierarchy,
  direction,
  handleType,
  position,
  showRemoveButton,
  onRemove,
}: PortRowProps) {
  const { fillColor, borderColor, anyType, typeName } = computePortStyle(port, typeHierarchy);
  const portTop = portStartY + index * 20;
  const side = direction === "input" ? { left: -7 } : { right: -7 };
  const removeStyle =
    direction === "input" ? { left: 6, top: portTop - 1 } : { right: 6, top: portTop - 1 };
  return (
    <span className="group">
      <Handle
        id={port.name}
        type={handleType}
        position={position}
        className="!h-3.5 !w-3.5 !border-2"
        title={`${typeName}${port.description ? " — " + port.description : ""}`}
        style={{
          backgroundColor: anyType ? "#ffffff" : fillColor,
          borderColor,
          borderStyle: anyType ? "dashed" : "solid",
          top: portTop,
          ...side,
        }}
      />
      {showRemoveButton && (
        <button
          type="button"
          className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-100 text-[9px] text-red-500 opacity-0 transition-opacity hover:bg-red-200 group-hover:opacity-100"
          title={`Remove port "${port.name}"`}
          style={removeStyle}
          onClick={() => onRemove(port.name)}
        >
          ×
        </button>
      )}
    </span>
  );
}

interface AddPortButtonProps {
  direction: Direction;
  portStartY: number;
  portCount: number;
  onAdd: () => void;
}

function AddPortButton({ direction, portStartY, portCount, onAdd }: AddPortButtonProps) {
  // translate(±50%, -50%) matches React Flow's <Handle> convention so the
  // button center aligns with the port-handle column.
  const side =
    direction === "input"
      ? { left: -7, transform: "translate(-50%, -50%)" }
      : { right: -7, transform: "translate(50%, -50%)" };
  return (
    <button
      type="button"
      className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-stone-100 text-[9px] text-stone-500 transition-colors hover:bg-ember hover:text-white"
      title={direction === "input" ? "Add input port" : "Add output port"}
      style={{ top: portStartY + portCount * 20, ...side }}
      onClick={onAdd}
    >
      +
    </button>
  );
}

interface PortHandlesProps {
  nodeId: string;
  data: BlockNodeData;
  effectiveInputPorts: BlockPortResponse[];
  effectiveOutputPorts: BlockPortResponse[];
  portStartY: number;
  isVariadicInputs: boolean;
  isVariadicOutputs: boolean;
  canAddInput: boolean;
  canRemoveInput: boolean;
  canAddOutput: boolean;
  canRemoveOutput: boolean;
}

export function PortHandles({
  nodeId,
  data,
  effectiveInputPorts,
  effectiveOutputPorts,
  portStartY,
  isVariadicInputs,
  isVariadicOutputs,
  canAddInput,
  canRemoveInput,
  canAddOutput,
  canRemoveOutput,
}: PortHandlesProps) {
  const typeHierarchy = data.schema?.type_hierarchy;
  const edges = useEdges();
  const { deleteElements } = useReactFlow();

  // Issue #1325: opening the add-port dialog defers the actual port
  // append until the user confirms a name + type. ``addPortDirection``
  // is the dialog's open / direction state; ``null`` keeps it closed.
  const [addPortDirection, setAddPortDirection] = useState<Direction | null>(null);

  const portsConfigFor = (direction: Direction): Array<{ name: string; types: string[] }> => {
    const key = direction === "input" ? "input_ports" : "output_ports";
    const current = data.config?.[key];
    return Array.isArray(current) ? (current as Array<{ name: string; types: string[] }>) : [];
  };

  // Issue #1325 P1 (Codex review): variadic blocks with static defaults
  // (Code Block's ``data``/``result``) must NOT lose those defaults the
  // first time the user adds or removes a port. The wire contract:
  // ``flowNodeBuilder.resolveVariadicPorts`` replaces the schema-level
  // ports wholesale once ``config.{input,output}_ports`` is non-empty.
  // Without this seed, the first add-port writes only the new entry to
  // config, the resolver replaces ``data``/``result``, and any existing
  // edges attached to those static names break.
  //
  // Mitigation: when the per-instance config is still empty, seed it
  // with the current EFFECTIVE port list (which already reflects any
  // ADR-028 dynamic-port type substitution) before applying the mutation.
  // Subsequent adds / removes operate on the now-populated config.
  const seedFromEffectiveIfEmpty = (
    direction: Direction,
  ): Array<{ name: string; types: string[] }> => {
    const current = portsConfigFor(direction);
    if (current.length > 0) return current;
    const effective = direction === "input" ? effectiveInputPorts : effectiveOutputPorts;
    return effective.map((p) => ({ name: p.name, types: p.accepted_types ?? [] }));
  };

  const handleAddPortConfirmed = (direction: Direction, name: string, typeName: string) => {
    const key = direction === "input" ? "input_ports" : "output_ports";
    const base = seedFromEffectiveIfEmpty(direction);
    data.onUpdateConfig?.({
      [key]: [...base, { name, types: [typeName] }],
    });
    setAddPortDirection(null);
  };

  const handleRemovePort = (direction: Direction, portName: string) => {
    const connected = edges.filter(
      (e: Edge) =>
        (direction === "input" && e.target === nodeId && e.targetHandle === portName) ||
        (direction === "output" && e.source === nodeId && e.sourceHandle === portName),
    );
    if (connected.length > 0) {
      const confirmed = window.confirm(
        `This port has ${connected.length} connection(s). Remove port and disconnect?`,
      );
      if (!confirmed) return;
      deleteElements({ edges: connected });
    }
    const key = direction === "input" ? "input_ports" : "output_ports";
    // Same seeding concern as ``handleAddPortConfirmed``: a remove on a
    // not-yet-seeded variadic block must operate on the effective list,
    // not on an empty config (which would otherwise leave config empty
    // and silently restore the just-removed static default).
    const base = seedFromEffectiveIfEmpty(direction);
    data.onUpdateConfig?.({ [key]: base.filter((p) => p.name !== portName) });
  };

  return (
    <>
      {effectiveInputPorts.map((port, index) => (
        <PortRow
          key={port.name}
          port={port}
          index={index}
          portStartY={portStartY}
          typeHierarchy={typeHierarchy}
          direction="input"
          handleType="target"
          position={Position.Left}
          showRemoveButton={isVariadicInputs && canRemoveInput}
          onRemove={(name) => handleRemovePort("input", name)}
        />
      ))}
      {isVariadicInputs && canAddInput && (
        <AddPortButton
          direction="input"
          portStartY={portStartY}
          portCount={effectiveInputPorts.length}
          onAdd={() => setAddPortDirection("input")}
        />
      )}
      {effectiveOutputPorts.map((port, index) => (
        <PortRow
          key={port.name}
          port={port}
          index={index}
          portStartY={portStartY}
          typeHierarchy={typeHierarchy}
          direction="output"
          handleType="source"
          position={Position.Right}
          showRemoveButton={isVariadicOutputs && canRemoveOutput}
          onRemove={(name) => handleRemovePort("output", name)}
        />
      ))}
      {isVariadicOutputs && canAddOutput && (
        <AddPortButton
          direction="output"
          portStartY={portStartY}
          portCount={effectiveOutputPorts.length}
          onAdd={() => setAddPortDirection("output")}
        />
      )}
      {addPortDirection && (
        <AddPortDialog
          direction={addPortDirection}
          allowedTypes={
            addPortDirection === "input"
              ? (data.schema?.allowed_input_types ?? [])
              : (data.schema?.allowed_output_types ?? [])
          }
          typeHierarchy={data.schema?.type_hierarchy}
          defaultName={`port_${portsConfigFor(addPortDirection).length + 1}`}
          onCancel={() => setAddPortDirection(null)}
          onSubmit={(name, typeName) => handleAddPortConfirmed(addPortDirection, name, typeName)}
        />
      )}
    </>
  );
}
