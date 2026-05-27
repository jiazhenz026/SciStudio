// BlockNode — canvas node for a SciStudio block instance.
//
// Refactored under #1422 to delegate to focused sub-modules in
// ./BlockNode.parts/. The discriminator for inline-config widgets, the
// status badge, the lazy file-picker modal, and the port-rendering logic
// all live in dedicated files. This module owns:
//   - the top-level BlockNode component (header / footer JSX, schema-driven
//     port-row layout measurement),
//   - per-instance computations that drive the sub-modules (effective ports,
//     capability filtering, port-row start Y measurement).
//
// Wave 1 (#1420/#1421) discipline preserved:
//   - InlineConfigField's default branch is delegated to
//     `InlineTextInputField`, keeping every hook chain at the top level of
//     its own component (rules-of-hooks).
//   - The two useLayoutEffect calls below carry the same eslint-disable
//     rationale as before — the inline measurement effect only depends on
//     list lengths, not on the node's full render output.

import { type Node, type NodeProps } from "@xyflow/react";
import { useLayoutEffect, useRef, useState } from "react";

import type { FormatCapabilityResponse, TypeHierarchyEntry } from "../../types/api";
import type { BlockNodeData } from "../../types/ui";
import { computeEffectivePorts } from "../../utils/computeEffectivePorts";
import { LossySaveWarning } from "../WorkflowEditor/LossySaveWarning";

import { ErrorMessage } from "./BlockNode.parts/ErrorMessage";
import { InlineCapabilitySelector } from "./BlockNode.parts/InlineCapabilitySelector";
import { InlineConfigField } from "./BlockNode.parts/InlineConfigField";
import { PausedToast } from "./BlockNode.parts/PausedToast";
import { PortHandles } from "./BlockNode.parts/PortHandles";
import { StatusBadge } from "./BlockNode.parts/StatusBadge";
import { categoryIcons } from "./BlockNode.parts/badgeStyles";
import { getTopConfigProperties } from "./BlockNode.parts/inlineConfigHelpers";

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
  selectedType: string | null,
  typeHierarchy: TypeHierarchyEntry[],
): FormatCapabilityResponse[] {
  if (!selectedType) return capabilities;
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

function coreTypeFromConfig(
  configProps: ReturnType<typeof getTopConfigProperties>,
  config: BlockNodeData["config"],
): string | null {
  const coreTypeConfig = configProps.find((prop) => prop.key === "core_type")?.schema;
  if (typeof config?.core_type === "string") return config.core_type;
  if (typeof coreTypeConfig?.default === "string") return coreTypeConfig.default;
  return null;
}

function dynamicPortConfigValue(
  configProps: ReturnType<typeof getTopConfigProperties>,
  config: BlockNodeData["config"],
  sourceConfigKey: string | undefined,
): string | undefined {
  if (sourceConfigKey == null) return undefined;
  const configured = config?.[sourceConfigKey];
  if (typeof configured === "string" && configured) return configured;
  const schemaDefault = configProps.find((prop) => prop.key === sourceConfigKey)?.schema.default;
  return typeof schemaDefault === "string" && schemaDefault ? schemaDefault : undefined;
}

export function BlockNode({ id: nodeId, data, selected }: NodeProps<Node<BlockNodeData>>) {
  // ADR-028 Addendum 1 §B fix #2 / §C11: hide the ``direction`` config
  // field for any IO block (not just the legacy abstract-base type_name).
  // ``direction`` is a ClassVar on the IOBlock subclass — it is not a
  // user-editable runtime config field — so it must not be rendered in
  // any IO block's inline config strip.
  const configProps = getTopConfigProperties(data.schema?.config_schema).filter(
    (prop) => !(data.category === "io" && prop.key === "direction"),
  );
  // Fix #1307: when the block has a ``core_type`` driving config (LoadData /
  // SaveData), the inline Format dropdown MUST only show capabilities whose
  // ``data_type`` matches the active core_type, otherwise the user can pick
  // illegal combinations (e.g. core_type=Series + capability_id=
  // ``core.dataframe.csv.save``) that produce undefined runtime behaviour.
  // Blocks without a ``core_type`` field (e.g. imaging.threshold) are
  // unaffected because the filter is a no-op when ``coreType`` is null.
  const allFormatCapabilities = data.schema?.format_capabilities ?? [];
  const coreType = coreTypeFromConfig(configProps, data.config);
  const formatCapabilities = capabilitiesForType(
    allFormatCapabilities,
    coreType,
    data.schema?.type_hierarchy ?? [],
  );
  const categoryIcon = categoryIcons[data.category] ?? categoryIcons.custom;
  // ADR-028 Addendum 1 §B fix #3 / §C8: read ``direction`` from the schema
  // (class-level ClassVar, populated by the backend at scan time) instead
  // of from ``data.config?.direction``. After ADR-028 there is no runtime
  // ``direction`` config value — reading the old path always returned
  // undefined, breaking the Save Block directory picker.
  // ADR-028 Addendum 1 §D4 / spec §d step 4: compute effective ports from
  // the dynamic-port descriptor + driving config value. Static blocks pay
  // zero cost (the helper returns ``basePorts`` by reference). Dynamic
  // blocks (e.g. ``LoadData``) get per-instance ``accepted_types`` so the
  // port colour resolved by ``resolveTypeColor()`` updates live as the
  // user changes the dropdown.
  const dynamicPorts = data.schema?.dynamic_ports ?? null;
  const sourceConfigKey = dynamicPorts?.source_config_key;
  const drivingConfigValue = dynamicPortConfigValue(configProps, data.config, sourceConfigKey);
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

  // Measure the header height so port handles can hang off the LEFT/RIGHT
  // edges starting just below the first horizontal divider (i.e. aligned
  // with the inline-config rows) instead of being stacked below the entire
  // config block. The previous "below config" layout left the lower half
  // of the node empty when there were 1–3 ports, wasting vertical space.
  // Ports stick into the block by only 7px (handle is positioned at
  // ``left: -7`` / ``right: -7``) which sits inside the config rows'
  // ``px-3`` padding margin without overlapping the input widgets.
  //
  // We measure the config section's ``offsetTop`` (= bottom edge of the
  // header) and add 14px so port row 1 lands roughly on the vertical
  // centre of the first inline-config field. Subsequent ports stride by
  // 20px so 3 ports cover the typical 3-row inline-config strip.
  //
  // Variadic blocks (DataRouter etc.) usually have no inline-config rows
  // and may render 5+ ports. Those ports cascade down from the top; if
  // their count exceeds the natural block height, they extend past the
  // footer just like they did under the previous layout — handle this in
  // the PortEditor in the BottomPanel rather than dynamically resizing
  // the node here.
  const configSectionRef = useRef<HTMLDivElement>(null);
  const [portStartY, setPortStartY] = useState(50);
  useLayoutEffect(() => {
    if (configSectionRef.current) {
      // ``offsetTop`` is the header-bottom Y in the node's local
      // coordinate system (unaffected by ReactFlow's zoom transform).
      // Add 14px to centre port row 1 on the first config row.
      const offset = configSectionRef.current.offsetTop + 14;
      setPortStartY(offset);
    }
    // Re-measure only when config properties or port lists change, not on
    // every render (which causes port jitter during edge dragging).
  }, [configProps.length, effectiveInputPorts.length, effectiveOutputPorts.length]);

  const handleConfigChange = (key: string, value: unknown) => {
    data.onUpdateConfig?.(
      key === sourceConfigKey ? { [key]: value, capability_id: null } : { [key]: value },
    );
  };

  // ADR-029 D2: variadic port UI — [+] and [-] controls.
  // ADR-029 Addendum 1: min/max port count limits.
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

  return (
    <div
      className={`w-[280px] rounded-xl border bg-white shadow-sm ${
        selected ? "border-ember shadow-panel" : "border-stone-200"
      }`}
    >
      {/* ----------------------------------------------------------------- */}
      {/* Header                                                            */}
      {/* ----------------------------------------------------------------- */}
      <div className="flex items-center justify-between gap-2 border-b border-stone-100 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-base leading-none">{categoryIcon}</span>
          <span className="truncate font-display text-sm font-semibold text-ink">{data.label}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-stone-100 hover:text-ink"
            title="Run block"
            onClick={() => data.onRun?.()}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4 2.5v11l9-5.5z" />
            </svg>
          </button>
          <button
            type="button"
            className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-stone-100 hover:text-ink"
            title="Restart block"
            onClick={() => data.onRestart?.()}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M13 8a5 5 0 1 1-1.5-3.5M13 3v2.5h-2.5" />
            </svg>
          </button>
          <button
            type="button"
            className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-500"
            title="Remove block"
            onClick={() => data.onDelete?.()}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Inline config                                                     */}
      {/* ----------------------------------------------------------------- */}
      <div
        ref={configSectionRef}
        className="nodrag nowheel space-y-2 overflow-hidden border-b border-stone-100 px-3 py-2"
      >
        {configProps.length > 0
          ? configProps.map((prop) => (
              <InlineConfigField
                key={prop.key}
                prop={prop}
                value={data.config?.[prop.key]}
                onChange={handleConfigChange}
              />
            ))
          : null}
        {formatCapabilities.length > 0 ? (
          <InlineCapabilitySelector
            capabilities={formatCapabilities}
            value={data.config?.capability_id}
            onChange={(capabilityId) => data.onUpdateConfig?.({ capability_id: capabilityId })}
          />
        ) : configProps.length === 0 ? (
          <p className="text-center text-[11px] italic text-stone-400">No parameters</p>
        ) : null}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Port handles (positioned absolutely by React Flow)                */}
      {/* ----------------------------------------------------------------- */}
      {/* Use effective ports so dynamic blocks (LoadData, SaveData) get   */}
      {/* per-instance accepted_types resolved from data.schema?.dynamic_ports */}
      {/* + the current driving config value (ADR-028 Addendum 1 §D4).      */}
      <PortHandles
        nodeId={nodeId}
        data={data}
        effectiveInputPorts={effectiveInputPorts}
        effectiveOutputPorts={effectiveOutputPorts}
        portStartY={portStartY}
        isVariadicInputs={isVariadicInputs}
        isVariadicOutputs={isVariadicOutputs}
        canAddInput={canAddInput}
        canRemoveInput={canRemoveInput}
        canAddOutput={canAddOutput}
        canRemoveOutput={canRemoveOutput}
      />

      {/* ----------------------------------------------------------------- */}
      {/* Footer                                                            */}
      {/* ----------------------------------------------------------------- */}
      <div className="border-t border-stone-100 px-3 py-2">
        <div className="flex min-w-0 items-center">
          <StatusBadge status={data.status} onErrorClick={data.onErrorClick} />
          {data.status === "error" && (data.errorSummary ?? data.errorMessage) ? (
            <ErrorMessage message={data.errorSummary ?? data.errorMessage!} />
          ) : null}
        </div>
        {/* ADR-043 FR-014 — lossy-save warning chip. Only rendered for
            save-direction IO blocks where the parent has supplied
            `upstreamOmeFields` AND a capability is selected whose
            `metadata_fidelity` would drop any of those fields. The
            LossySaveWarning component itself returns null when the
            dropped-field set is empty, so this branch is cheap when
            there is no warning to surface. */}
        {data.category === "io" &&
          (data.schema?.direction === "output" || data.schema?.direction === "save") &&
          data.upstreamOmeFields &&
          data.upstreamOmeFields.length > 0 &&
          (() => {
            const selectedId = data.config?.capability_id;
            const selectedCap =
              formatCapabilities.find(
                (c) => typeof selectedId === "string" && c.id === selectedId,
              ) ?? (formatCapabilities.length === 1 ? formatCapabilities[0] : undefined);
            if (!selectedCap) return null;
            return (
              <div className="mt-1">
                <LossySaveWarning
                  sourceOmeFields={data.upstreamOmeFields}
                  targetCapabilityFidelity={selectedCap.metadata_fidelity}
                />
              </div>
            );
          })()}
        {data.status === "paused" && data.category === "app" && (
          <PausedToast outputDir={String(data.config?.output_dir ?? "")} />
        )}
        {data.status === "paused" && data.category !== "app" && (
          <div className="mt-1 flex items-center gap-1 rounded border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] text-blue-700">
            Waiting for user input...
          </div>
        )}
      </div>
    </div>
  );
}
