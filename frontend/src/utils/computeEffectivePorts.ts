/**
 * Pure-function helper that resolves the effective ``accepted_types`` for
 * each port of a block whose ports depend on a config field selection.
 *
 * Implements the frontend half of ADR-028 Addendum 1 §D4 / §C5. The backend
 * already populates ``BlockSchemaResponse.dynamic_ports`` with the
 * declarative enum-mapping descriptor; this helper consumes it locally so
 * port colors update live as the user changes the driving dropdown — no
 * backend round-trip required.
 *
 * Static blocks (``dynamicPorts == null``) and blocks whose driving config
 * value is unset receive the original ``basePorts`` unchanged. The function
 * is intentionally a pure mapping with no side effects so it is trivial to
 * test and trivial to call inside a React render path.
 *
 * Per ``docs/specs/phase11-implementation-standards.md`` T-TRK-009.
 */

import type { BlockPortResponse, BlockSchemaResponse, DynamicPortsConfig } from "../types/api";

export type { DynamicPortsConfig };

/**
 * Read the dynamic-port driving config value (e.g. LoadData ``core_type``)
 * from the node's params envelope, falling back to the schema default.
 *
 * #2141: this resolution MUST be shared by every surface that colours ports
 * or edges. ``BlockNode`` previously fell back to the schema default while
 * ``WorkflowCanvas`` did not, so a freshly dropped Load block (whose
 * ``core_type`` is never materialized into ``config.params``) rendered an
 * amber DataFrame port with a gray DataObject edge. One helper, one answer.
 *
 * The user edits the driving field in BottomPanel Config; the canvas only
 * reads it to colour ports and edges.
 *
 * @param config - the node's params envelope (``node.config.params``; the
 *   ``BlockNodeData.config`` field already carries exactly this envelope)
 * @param schema - the block schema, consulted for the config-schema default
 * @param sourceConfigKey - ``schema.dynamic_ports.source_config_key``
 * @returns the configured string value, else the schema default, else
 *   ``undefined``
 */
export function resolveDrivingConfigValue(
  config: Record<string, unknown> | undefined,
  schema: BlockSchemaResponse | undefined,
  sourceConfigKey: string | undefined,
): string | undefined {
  if (sourceConfigKey == null) return undefined;
  const configured = config?.[sourceConfigKey];
  if (typeof configured === "string" && configured) return configured;
  const properties = schema?.config_schema?.properties;
  const schemaDefault = properties?.[sourceConfigKey]?.default;
  return typeof schemaDefault === "string" && schemaDefault ? schemaDefault : undefined;
}

/**
 * Compute the effective port list for a block instance.
 *
 * @param dynamicPorts - the descriptor from ``schema.dynamic_ports``, or
 *   ``null``/``undefined`` for static blocks
 * @param configValue - the current value of the driving config field
 *   (``schema.dynamic_ports.source_config_key``), or ``undefined`` if unset
 * @param basePorts - the class-level placeholder ports from
 *   ``schema.input_ports`` / ``schema.output_ports``
 * @param kind - which mapping to consult (``"input"`` reads
 *   ``input_port_mapping``; ``"output"`` reads ``output_port_mapping``)
 * @returns a new array of ports with ``accepted_types`` overridden when the
 *   descriptor has a rule for that port and that enum value, or the
 *   original ``basePorts`` (referentially equal) when no override applies
 */
export function computeEffectivePorts(
  dynamicPorts: DynamicPortsConfig | null | undefined,
  configValue: string | undefined,
  basePorts: BlockPortResponse[],
  kind: "input" | "output",
): BlockPortResponse[] {
  // Static block: no descriptor at all.
  if (!dynamicPorts) return basePorts;
  // Driving config value is unset (e.g. user has not yet picked from the
  // dropdown). Return the placeholder ClassVar ports.
  if (!configValue) return basePorts;

  const mapping =
    kind === "input" ? dynamicPorts.input_port_mapping : dynamicPorts.output_port_mapping;

  // Mismatched kind: descriptor only declares the opposite direction's
  // mapping (e.g. caller asked for "input" but only output_port_mapping is
  // set). Falling back to base ports is intentional — this is a valid case
  // for blocks like LoadData that drive output but have no input ports.
  if (!mapping) return basePorts;

  return basePorts.map((port) => {
    const portRules = mapping[port.name];
    // No rules for this specific port — leave it unchanged. This lets a
    // descriptor override only one port among several.
    if (!portRules) return port;
    const acceptedTypes = portRules[configValue];
    // Unknown enum value (e.g. user-typed value not in the schema enum, or
    // a stale config from before a backend enum change). Fall back to the
    // base port's accepted_types instead of throwing.
    if (!acceptedTypes) return port;
    return { ...port, accepted_types: acceptedTypes };
  });
}
