import type {
  BlockSchemaResponse,
  FormatCapabilityResponse,
  TypeHierarchyEntry,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import { type PortRow, PortEditorTable } from "../PortEditorTable";
import { lossyOmeFields } from "../../api/capabilities";
import { LossySaveWarning, collectUpstreamOmeFields } from "../WorkflowEditor/LossySaveWarning";

import { CodeBlockConfigEditor } from "./CodeBlockConfigEditor";
import { ConfigField } from "./ConfigField";
import { FormatCapabilityConfig } from "./FormatCapabilityConfig";
import { isCodeBlockConfigTarget } from "./codeBlockPorts";

function ancestorTypeNames(typeName: string, typeHierarchy: TypeHierarchyEntry[]): Set<string> {
  const ancestors = new Set<string>();
  if (!typeName) return ancestors;
  ancestors.add(typeName);
  const index = new Map(typeHierarchy.map((entry) => [entry.name, entry]));
  let current = index.get(typeName);
  while (current?.base_type && !ancestors.has(current.base_type)) {
    ancestors.add(current.base_type);
    current = index.get(current.base_type);
  }
  return ancestors;
}

function capabilitiesForType(
  capabilities: FormatCapabilityResponse[],
  selectedType: string,
  typeHierarchy: TypeHierarchyEntry[],
): FormatCapabilityResponse[] {
  if (!selectedType) return [];
  const acceptedTypes = ancestorTypeNames(selectedType, typeHierarchy);
  const filtered = capabilities.filter((capability) => acceptedTypes.has(capability.data_type));
  if (!acceptedTypes.has("Artifact")) return filtered;
  let artifactInserted = false;
  return filtered.flatMap((capability) => {
    if (capability.data_type !== "Artifact") return [capability];
    if (artifactInserted) return [];
    artifactInserted = true;
    return [
      {
        ...capability,
        id: `core.artifact.any.${capability.direction}`,
        data_type: "Artifact",
        format_id: "any",
        extensions: [],
        label: "Any",
        is_default: true,
        roundtrip_group: null,
        is_synthesized: false,
        migration_scaffold: false,
      },
    ];
  });
}

function orderedConfigEntries(
  schema: BlockSchemaResponse | undefined,
  selectedNode: WorkflowNode | null,
): Array<[string, Record<string, unknown>]> {
  const properties = schema?.config_schema.properties ?? {};
  return Object.entries(properties)
    .filter(([key, value]) => {
      // For io_block, hide "direction" — it is already determined by whether
      // the user dragged a Load Block or Save Block from the palette.
      if ((schema?.direction || selectedNode?.block_type === "io_block") && key === "direction") {
        return false;
      }
      if (key === "capability_id") return false;
      // Skip port_editor fields — rendered separately as PortEditorTable below.
      if ((value as Record<string, unknown>).ui_widget === "port_editor") return false;
      return true;
    })
    .sort(([, left], [, right]) => {
      return Number(left.ui_priority ?? 99) - Number(right.ui_priority ?? 99);
    }) as Array<[string, Record<string, unknown>]>;
}

/**
 * ADR-050 FR-014 — collect the union of upstream OME field paths that feed
 * the selected node, by walking every edge whose target is this node back to
 * the source block's cached outputs. Mirrors
 * ``flowNodeBuilder.computeUpstreamOmeFields`` but lives here so the
 * BottomPanel Config detail does not depend on a WorkflowCanvas-owned file
 * (the canvas no longer renders the lossy-save chip per ADR-050 §2.3/§2.5).
 *
 * Edge endpoints carry a ``"<nodeId>:<port>"`` suffix; the node id is the
 * portion before the first ``:``.
 */
function upstreamOmeFieldsFor(
  nodeId: string,
  edges: WorkflowEdge[] | undefined,
  blockOutputs: Record<string, Record<string, unknown>> | undefined,
): string[] {
  if (!edges || !blockOutputs) return [];
  const sourceIds = edges
    .filter((edge) => edge.target.split(":")[0] === nodeId)
    .map((edge) => edge.source.split(":")[0]);
  if (sourceIds.length === 0) return [];
  const collected = new Set<string>();
  for (const sourceId of sourceIds) {
    const outputs = blockOutputs[sourceId];
    if (!outputs) continue;
    for (const field of collectUpstreamOmeFields(outputs)) {
      collected.add(field);
    }
  }
  return Array.from(collected);
}

/**
 * ADR-050 FR-014 — resolve the capability whose ``metadata_fidelity`` governs
 * the lossy-save check for the selected save node: the explicitly pinned
 * ``capability_id`` when present, otherwise the sole capability when exactly
 * one matches. Returns ``undefined`` when the selection is ambiguous.
 */
function selectedSaveCapability(
  capabilities: FormatCapabilityResponse[],
  capabilityId: unknown,
): FormatCapabilityResponse | undefined {
  if (typeof capabilityId === "string") {
    const pinned = capabilities.find((capability) => capability.id === capabilityId);
    if (pinned) return pinned;
  }
  if (capabilities.length === 1) return capabilities[0];
  return undefined;
}

function isSaveDirectionIoNode(schema: BlockSchemaResponse): boolean {
  return (
    schema.base_category === "io" && (schema.direction === "output" || schema.direction === "save")
  );
}

export function ConfigPanel({
  selectedNode,
  schema,
  onUpdateConfig,
  blockOutputs,
  edges,
}: {
  selectedNode: WorkflowNode | null;
  schema?: BlockSchemaResponse;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  /**
   * ADR-050 FR-014 — ``blockId -> output payload`` map used to compute the
   * upstream OME fields that feed the selected save node. OPTIONAL so the
   * panel type-checks standalone and degrades gracefully (no lossy detail)
   * when FE-2's wiring has not supplied it yet.
   */
  blockOutputs?: Record<string, Record<string, unknown>>;
  /**
   * ADR-050 FR-014 — workflow edges used to resolve which upstream blocks
   * feed the selected node. OPTIONAL for the same reason as ``blockOutputs``.
   */
  edges?: WorkflowEdge[];
}) {
  const params = ((selectedNode?.config.params as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;
  const ordered = orderedConfigEntries(schema, selectedNode);

  if (!selectedNode || !schema) {
    return <div className="text-sm text-stone-500">Select a block to edit its settings.</div>;
  }

  if (isCodeBlockConfigTarget(selectedNode, schema)) {
    return (
      <CodeBlockConfigEditor
        onUpdateConfig={onUpdateConfig}
        params={params}
        typeHierarchy={schema.type_hierarchy ?? []}
      />
    );
  }

  const isVariadicInputs = schema.variadic_inputs === true;
  const isVariadicOutputs = schema.variadic_outputs === true;
  const inputPorts = Array.isArray(params["input_ports"])
    ? (params["input_ports"] as PortRow[])
    : [];
  const outputPorts = Array.isArray(params["output_ports"])
    ? (params["output_ports"] as PortRow[])
    : [];
  const typeHierarchy = schema.type_hierarchy ?? [];
  const allowedInputTypes = schema.allowed_input_types ?? [];
  const allowedOutputTypes = schema.allowed_output_types ?? [];
  const formatCapabilities = schema.format_capabilities ?? [];
  const coreTypeSchema = schema.config_schema.properties?.core_type;
  const hasCoreTypeField = coreTypeSchema != null;
  // The format-capability picker is a tall control (dropdown + detail +
  // warnings), so it renders after the LAST config field as its own half-row
  // cell. This keeps the short fields packed in 2-column pairs above it (e.g.
  // save_data: Filename and Overwrite sit together) instead of the format
  // height stranding a trailing field on its own row.
  const formatAnchorKey = ordered.length > 0 ? ordered[ordered.length - 1][0] : "core_type";
  const selectedType =
    typeof params.core_type === "string"
      ? params.core_type
      : typeof coreTypeSchema?.default === "string"
        ? coreTypeSchema.default
        : "";
  const visibleFormatCapabilities = hasCoreTypeField
    ? capabilitiesForType(formatCapabilities, selectedType, typeHierarchy)
    : formatCapabilities;
  const formatSelector =
    visibleFormatCapabilities.length > 0 ? (
      <FormatCapabilityConfig
        capabilities={visibleFormatCapabilities}
        onChange={(capabilityId) => onUpdateConfig({ capability_id: capabilityId })}
        value={params.capability_id}
      />
    ) : null;

  // ADR-050 FR-014 — lossy-save warning detail. The canvas square node no
  // longer renders this chip (ADR-050 §2.5); BottomPanel Config is the sole
  // surface for the validation detail. Only IO save-direction nodes whose
  // selected capability would drop upstream OME fields surface a warning;
  // LossySaveWarning itself returns null when the dropped-field set is empty.
  const lossySaveDetail = (() => {
    if (!isSaveDirectionIoNode(schema)) return null;
    const upstreamOmeFields = upstreamOmeFieldsFor(selectedNode.id, edges, blockOutputs);
    if (upstreamOmeFields.length === 0) return null;
    const selectedCapability = selectedSaveCapability(
      visibleFormatCapabilities,
      params.capability_id,
    );
    if (!selectedCapability) return null;
    // Gate the wrapper on the actual dropped-field set so we render no empty
    // detail container when the capability round-trips everything (lossless).
    if (lossyOmeFields(upstreamOmeFields, selectedCapability.metadata_fidelity).length === 0) {
      return null;
    }
    return (
      <div className="mb-4 max-w-2xl" data-testid="config-lossy-save-detail">
        <LossySaveWarning
          sourceOmeFields={upstreamOmeFields}
          targetCapabilityFidelity={selectedCapability.metadata_fidelity}
        />
      </div>
    );
  })();

  return (
    <div>
      {(isVariadicInputs || isVariadicOutputs) && (
        // Variadic ports are pinned to a 2-column row: column 1 is always
        // inputs, column 2 is always outputs. A missing side leaves its
        // column empty so the positions never shift. All variadic blocks
        // (and their subclasses) share this single render path.
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            {isVariadicInputs && (
              <PortEditorTable
                allowedTypes={allowedInputTypes}
                direction="input"
                maxPorts={schema.max_input_ports}
                minPorts={schema.min_input_ports}
                onChange={(ports) => onUpdateConfig({ input_ports: ports })}
                ports={inputPorts}
                typeHierarchy={typeHierarchy}
              />
            )}
          </div>
          <div>
            {isVariadicOutputs && (
              <PortEditorTable
                allowedTypes={allowedOutputTypes}
                direction="output"
                maxPorts={schema.max_output_ports}
                minPorts={schema.min_output_ports}
                onChange={(ports) => onUpdateConfig({ output_ports: ports })}
                ports={outputPorts}
                typeHierarchy={typeHierarchy}
              />
            )}
          </div>
        </div>
      )}
      {!hasCoreTypeField && formatSelector ? (
        <div className="mb-4 max-w-2xl">{formatSelector}</div>
      ) : null}
      {lossySaveDetail}
      <div className="grid gap-4 md:grid-cols-2">
        {ordered.map(([key, value]) => {
          const currentValue = params[key] ?? value.default ?? "";
          // Textarea fields (e.g. the AI prompt) take a tall left-column cell
          // that spans two rows, so neighbouring fields stack down its right.
          const isTextarea = (value as { ui_widget?: unknown }).ui_widget === "textarea";
          return (
            <div key={key} className="contents">
              {/* min-w-0 lets each half-row cell shrink to its grid track so a
                  long select option or capability warning cannot widen the
                  column and stretch the neighbouring field. */}
              <div className={isTextarea ? "min-w-0 md:row-span-2" : "min-w-0"}>
                <ConfigField
                  fieldKey={key}
                  field={value}
                  currentValue={currentValue}
                  onUpdateConfig={onUpdateConfig}
                />
              </div>
              {hasCoreTypeField && key === formatAnchorKey && formatSelector ? (
                <div className="min-w-0">{formatSelector}</div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
