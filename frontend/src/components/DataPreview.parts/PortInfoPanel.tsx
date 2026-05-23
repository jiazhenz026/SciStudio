// PortInfoPanel — right-side preview pane port descriptions.
//
// Spec: docs/specs/port-description-metadata.md (issue #1326).
// Renders the per-port `description` (from `BlockPortResponse.description`)
// for the selected block so users can distinguish multiple ports of the
// same data type (e.g. three Image inputs).
//
// Layout per spec §3:
//   [icon] TypeName              — when description is empty
//   [icon] TypeName — description — when description is non-empty
//   [icon] TypeName — <port name> — for user-added variadic ports
//
// Variadic detection: a port is treated as user-added when its `name`
// does NOT appear in the block's declared (schema-level) port name list.
// That declared list is `BlockSummary.input_ports[].name` aggregated from
// the block-spec; PortInfoPanel receives both the schema-level static
// names and the effective per-instance port list so it can pick the
// right row format without a new wire field.

import { primaryTypeName, resolveTypeColor } from "../../config/typeColorMap";
import type { BlockPortResponse, BlockSchemaResponse } from "../../types/api";

interface PortInfoPanelProps {
  /** Effective per-instance ports for the selected node, in declaration order. */
  inputPorts: BlockPortResponse[];
  outputPorts: BlockPortResponse[];
  /** Block schema (used for the type-hierarchy → color lookup and for the
   *  declared port-name set that distinguishes static vs user-added rows). */
  schema?: BlockSchemaResponse;
}

interface RowProps {
  port: BlockPortResponse;
  typeHierarchy: BlockSchemaResponse["type_hierarchy"] | undefined;
  declaredNames: Set<string>;
}

function describePort(port: BlockPortResponse, declaredNames: Set<string>): string | null {
  // Author-defined port with a non-empty description: show the description.
  if (port.description) return port.description;
  // User-added variadic port: name is NOT in the schema-level declared
  // list. Fall back to the user-typed port name as the descriptive text.
  if (!declaredNames.has(port.name)) return port.name;
  // Author-defined port with an empty description: no descriptive text.
  return null;
}

function PortRow({ port, typeHierarchy, declaredNames }: RowProps) {
  const color = resolveTypeColor(port.accepted_types, typeHierarchy);
  const typeName = primaryTypeName(port.accepted_types) || "Any";
  const text = describePort(port, declaredNames);
  return (
    <li className="flex items-baseline gap-2 py-1 text-xs text-stone-700">
      <span
        aria-hidden
        className="mt-1 inline-block h-2 w-2 flex-shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="font-medium text-stone-800">{typeName}</span>
      {text != null && (
        <>
          <span className="text-stone-400">—</span>
          <span className="text-stone-600">{text}</span>
        </>
      )}
    </li>
  );
}

export function PortInfoPanel({ inputPorts, outputPorts, schema }: PortInfoPanelProps) {
  const typeHierarchy = schema?.type_hierarchy;
  // Declared (static) port names from the block's BlockSpec. Anything in
  // the effective list whose name is NOT here is a variadic addition the
  // user authored at runtime — those rows fall back to the user-typed
  // name as descriptive text per spec §3 / §5.
  const declaredInputs = new Set<string>(schema?.input_ports.map((p) => p.name) ?? []);
  const declaredOutputs = new Set<string>(schema?.output_ports.map((p) => p.name) ?? []);

  // Hide the section header if its port list is empty so a block with
  // only inputs does not render an empty "Output Port:" header.
  const hasInputs = inputPorts.length > 0;
  const hasOutputs = outputPorts.length > 0;
  if (!hasInputs && !hasOutputs) return null;

  return (
    <section
      aria-label="Port descriptions"
      className="mt-4 border-t border-stone-200 pt-3"
      data-testid="port-info-panel"
    >
      {hasInputs && (
        <>
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Input Port</p>
          <ul className="mt-1">
            {inputPorts.map((port) => (
              <PortRow
                key={`in-${port.name}`}
                port={port}
                typeHierarchy={typeHierarchy}
                declaredNames={declaredInputs}
              />
            ))}
          </ul>
        </>
      )}
      {hasOutputs && (
        <>
          <p className={`text-xs uppercase tracking-[0.2em] text-stone-500 ${hasInputs ? "mt-3" : ""}`}>
            Output Port
          </p>
          <ul className="mt-1">
            {outputPorts.map((port) => (
              <PortRow
                key={`out-${port.name}`}
                port={port}
                typeHierarchy={typeHierarchy}
                declaredNames={declaredOutputs}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
