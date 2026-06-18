// Extracted from BlockNode.tsx as part of the #1422 god-file split.
//
// PortHandles — renders the input + output ReactFlow `Handle`s for a block
// node along with the variadic add/remove controls.
//
//   - ADR-050 §2.4: input ports sit on the left rail, output ports on the
//     right rail of the fixed 104px square. Each handle's Y comes from
//     `portRailOffset(index, count)` in `nodeGeometry.ts` so rails align to
//     the square; rails MAY extend below the square for many ports but the
//     body stays fixed (ADR-050 §2.4). The handles hang just OUTSIDE the body
//     edge (`left: -7` / `right: -7`).
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
import {
  type CodeBlockPortConfig,
  type CodeBlockPortDirection,
  codeBlockPortFromVariadicEntry,
  isCodeBlockConfigTarget,
  persistCodeBlockPort,
} from "../../BottomPanel.parts/codeBlockPorts";

import { AddPortDialog } from "./AddPortDialog";
import { addPortRailOffset, portRailOffset } from "./nodeGeometry";

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
  /** Total ports on this rail — drives `portRailOffset` centring. */
  portCount: number;
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
  portCount,
  typeHierarchy,
  direction,
  handleType,
  position,
  showRemoveButton,
  onRemove,
}: PortRowProps) {
  const { fillColor, borderColor, anyType, typeName } = computePortStyle(port, typeHierarchy);
  // ADR-050 §2.4 — Y comes from the square's port-rail geometry, not from a
  // measured inline-config row (the inline config strip no longer exists).
  const portTop = portRailOffset(index, portCount);
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
  portCount: number;
  onAdd: () => void;
}

function AddPortButton({ direction, portCount, onAdd }: AddPortButtonProps) {
  // translate(±50%, -50%) matches React Flow's <Handle> convention so the
  // button center aligns with the port-handle column. The `+` sits one stride
  // past the last port on the rail (ADR-050 §2.4 — append affordance).
  const side =
    direction === "input"
      ? { left: -7, transform: "translate(-50%, -50%)" }
      : { right: -7, transform: "translate(50%, -50%)" };
  return (
    <button
      type="button"
      className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-stone-100 text-[9px] text-stone-500 transition-colors hover:bg-ember hover:text-white"
      title={direction === "input" ? "Add input port" : "Add output port"}
      style={{ top: addPortRailOffset(portCount), ...side }}
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

  // Hotfix 2026-05-23 (#1324 partial cover) — Code Block keeps a parallel
  // ``params.inputs`` / ``params.outputs`` list (full :class:`CodeBlockPortConfig`
  // shape used by the v2 runtime exchange) that drives the BottomPanel config
  // editor. Without mirror-writes the canvas "+" / "×" buttons updated only
  // ``input_ports`` / ``output_ports``, leaving the config-editor table stale.
  // Layout alignment is tracked separately in #1324.
  const isCodeBlock = isCodeBlockConfigTarget(null, data.schema);

  const v2KeyFor = (direction: Direction) => (direction === "input" ? "inputs" : "outputs");
  const v2PortsFor = (direction: Direction): CodeBlockPortConfig[] => {
    const raw = data.config?.[v2KeyFor(direction)];
    if (!Array.isArray(raw)) return [];
    const dir: CodeBlockPortDirection = direction;
    return raw.map((entry, index) => {
      const row = (typeof entry === "object" && entry !== null ? entry : {}) as Record<
        string,
        unknown
      >;
      return {
        name: String(row.name ?? `${dir}_${index + 1}`),
        direction: dir,
        data_type: String(row.data_type ?? "DataObject"),
        extension: String(row.extension ?? ".txt"),
        capability_id: row.capability_id == null ? "" : String(row.capability_id),
        required: typeof row.required === "boolean" ? row.required : true,
        exchange_folder: String(row.exchange_folder ?? ""),
      };
    });
  };

  const handleAddPortConfirmed = (direction: Direction, name: string, typeName: string) => {
    const key = direction === "input" ? "input_ports" : "output_ports";
    const base = seedFromEffectiveIfEmpty(direction);
    const patch: Record<string, unknown> = {
      [key]: [...base, { name, types: [typeName] }],
    };
    if (isCodeBlock) {
      const v2Key = v2KeyFor(direction);
      const v2Base = v2PortsFor(direction);
      const newV2Port = codeBlockPortFromVariadicEntry({ name, types: [typeName] }, direction);
      patch[v2Key] = [...v2Base, persistCodeBlockPort(newV2Port, direction)];
    }
    data.onUpdateConfig?.(patch);
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
    const patch: Record<string, unknown> = {
      [key]: base.filter((p) => p.name !== portName),
    };
    if (isCodeBlock) {
      const v2Key = v2KeyFor(direction);
      const v2Base = v2PortsFor(direction);
      patch[v2Key] = v2Base
        .filter((p) => p.name !== portName)
        .map((p) => persistCodeBlockPort(p, direction));
    }
    data.onUpdateConfig?.(patch);
  };

  return (
    <>
      {effectiveInputPorts.map((port, index) => (
        <PortRow
          key={port.name}
          port={port}
          index={index}
          portCount={effectiveInputPorts.length}
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
          portCount={effectiveInputPorts.length}
          onAdd={() => setAddPortDirection("input")}
        />
      )}
      {effectiveOutputPorts.map((port, index) => (
        <PortRow
          key={port.name}
          port={port}
          index={index}
          portCount={effectiveOutputPorts.length}
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
