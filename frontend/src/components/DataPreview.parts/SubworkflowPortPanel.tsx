// SubworkflowPortPanel — ADR-044 exposed-port provenance for a subworkflow node.
//
// A subworkflow node's exposed ports are named with the opaque dot form
// "<innerBlockId>.<port>" (e.g. "d_bl.spectra"), so from the parent canvas the
// user cannot tell which inner block a port belongs to. This panel lists each
// exposed input/output port alongside the human name of its owning inner block
// (and the inner port + data type), using the provenance the backend attaches
// to each `resolved_ports` entry (`block_label`/`block_id`/`port`).

import { primaryTypeName, resolveTypeColor } from "../../config/typeColorMap";
import type { BlockSchemaResponse, ResolvedSubworkflowPort } from "../../types/api";

interface SubworkflowPortPanelProps {
  inputs: ResolvedSubworkflowPort[];
  outputs: ResolvedSubworkflowPort[];
  /** Shared type hierarchy (any block schema's copy) for the port-type colour. */
  typeHierarchy?: BlockSchemaResponse["type_hierarchy"];
}

function ownerLabel(port: ResolvedSubworkflowPort): string {
  // Prefer the block's display name; fall back to its id, then the exposed name.
  const block = port.block_label || port.block_id;
  const inner = port.port;
  if (block && inner) return `${block} · ${inner}`;
  if (block) return block;
  return port.name;
}

function PortRow({
  port,
  typeHierarchy,
}: {
  port: ResolvedSubworkflowPort;
  typeHierarchy: BlockSchemaResponse["type_hierarchy"] | undefined;
}) {
  const color = resolveTypeColor(port.accepted_types, typeHierarchy);
  const typeName = primaryTypeName(port.accepted_types) || "Any";
  return (
    <li className="flex items-start gap-2 py-1.5 text-xs" data-testid="subworkflow-port-row">
      <span
        aria-hidden
        className="mt-1 inline-block h-2 w-2 flex-shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="min-w-0">
        <span className="block truncate font-mono font-medium text-stone-800" title={port.name}>
          {port.name}
        </span>
        <span className="block truncate text-stone-500" title={ownerLabel(port)}>
          {ownerLabel(port)}
          <span className="text-stone-400"> · {typeName}</span>
        </span>
      </span>
    </li>
  );
}

/**
 * Render the exposed-port → owning-block map for a subworkflow node. Returns
 * null when there are no exposed ports (e.g. a broken reference) so the preview
 * pane stays clean.
 */
export function SubworkflowPortPanel({
  inputs,
  outputs,
  typeHierarchy,
}: SubworkflowPortPanelProps) {
  const hasInputs = inputs.length > 0;
  const hasOutputs = outputs.length > 0;
  if (!hasInputs && !hasOutputs) return null;

  return (
    <section
      aria-label="Subworkflow exposed ports"
      className="mt-4 border-t border-stone-200 pt-3"
      data-testid="subworkflow-port-panel"
    >
      <p className="text-xs text-stone-500">
        Each exposed port maps to a port on an inner block of the referenced subworkflow.
      </p>
      {hasInputs && (
        <>
          <p className="mt-3 text-xs uppercase tracking-[0.2em] text-stone-500">Input Ports</p>
          <ul className="mt-1">
            {inputs.map((port) => (
              <PortRow key={`in-${port.name}`} port={port} typeHierarchy={typeHierarchy} />
            ))}
          </ul>
        </>
      )}
      {hasOutputs && (
        <>
          <p
            className={`text-xs uppercase tracking-[0.2em] text-stone-500 ${hasInputs ? "mt-3" : ""}`}
          >
            Output Ports
          </p>
          <ul className="mt-1">
            {outputs.map((port) => (
              <PortRow key={`out-${port.name}`} port={port} typeHierarchy={typeHierarchy} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
