import { useState } from "react";

import { api, ApiError } from "../../lib/api";
import type {
  BlockSchemaResponse,
  FormatCapabilityResponse,
  TypeHierarchyEntry,
  WorkflowNode,
} from "../../types/api";
import { type PortRow, PortEditorTable } from "../PortEditorTable";
import { FileBrowserModal } from "../nodes/BlockNode.parts/FileBrowserModal";

import { CaretPreservingTextInput } from "./CaretPreservingTextInput";
import { CodeBlockConfigEditor } from "./CodeBlockConfigEditor";
import { FormatCapabilityConfig } from "./FormatCapabilityConfig";
import { isCodeBlockConfigTarget } from "./codeBlockPorts";

type BrowseMode = "file" | "directory" | null;

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

function browseModeFor(uiWidget: string | undefined): BrowseMode {
  if (uiWidget === "file_browser") return "file";
  if (uiWidget === "directory_browser") return "directory";
  return null;
}

function nativeInitialDir(
  browseMode: NonNullable<BrowseMode>,
  current: string,
): string | undefined {
  if (!current) return undefined;
  const sep = current.includes("\\") ? "\\" : "/";
  const parts = current.split(sep);
  if (browseMode === "file" && parts.length > 1 && parts[parts.length - 1].includes(".")) {
    return parts.slice(0, -1).join(sep);
  }
  return current;
}

function shouldFallbackToInAppModal(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 504) {
      console.error(
        "Native file dialog timed out (HTTP 504); not falling back to in-app picker.",
        err,
      );
      return false;
    }
    return true;
  }
  return true;
}

function modalInitialPath(browseMode: NonNullable<BrowseMode>, current: string): string {
  if (!current) return "";
  const sep = current.includes("\\") ? "\\" : "/";
  const parts = current.split(sep);
  if (browseMode === "file" && parts.length > 1 && parts[parts.length - 1].includes(".")) {
    return parts.slice(0, -1).join(sep);
  }
  return current;
}

function EnumField({
  fieldKey,
  field,
  currentValue,
  onUpdateConfig,
}: {
  fieldKey: string;
  field: Record<string, unknown>;
  currentValue: unknown;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const enumValues = field.enum as unknown[];
  return (
    <label className="grid gap-2 text-sm" key={fieldKey}>
      <span className="font-medium text-ink">{String(field.title ?? fieldKey)}</span>
      <select
        className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
        onChange={(event) =>
          onUpdateConfig(
            fieldKey === "core_type"
              ? { [fieldKey]: event.target.value, capability_id: null }
              : { [fieldKey]: event.target.value },
          )
        }
        value={String(currentValue)}
      >
        {enumValues.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ScalarField({
  fieldKey,
  field,
  currentValue,
  onUpdateConfig,
}: {
  fieldKey: string;
  field: Record<string, unknown>;
  currentValue: unknown;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const [browseOpen, setBrowseOpen] = useState(false);
  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-3 text-sm" key={fieldKey}>
        <input
          checked={Boolean(currentValue)}
          className="h-4 w-4 rounded border-stone-300"
          onChange={(event) => onUpdateConfig({ [fieldKey]: event.target.checked })}
          type="checkbox"
        />
        <span className="font-medium text-ink">{String(field.title ?? fieldKey)}</span>
      </label>
    );
  }

  const uiWidget = field.ui_widget as string | undefined;
  const browseMode = browseModeFor(uiWidget);
  const applySelectedPath = (paths: string[]) => {
    if (paths.length === 0) return;
    const supportsArray = Array.isArray(field.type)
      ? field.type.includes("array")
      : field.type === "array";
    onUpdateConfig({
      [fieldKey]: supportsArray && paths.length > 1 ? paths : paths[0],
    });
  };
  const handleBrowseClick = async () => {
    if (!browseMode) return;
    try {
      const result = await api.openNativeDialog(
        browseMode,
        nativeInitialDir(browseMode, String(currentValue ?? "")),
      );
      applySelectedPath(result.paths);
    } catch (err) {
      if (shouldFallbackToInAppModal(err)) {
        setBrowseOpen(true);
      }
    }
  };
  return (
    <label className="grid gap-2 text-sm" key={fieldKey}>
      <span className="font-medium text-ink">{String(field.title ?? fieldKey)}</span>
      <div className="flex w-full min-w-0 items-stretch gap-2">
        <CaretPreservingTextInput
          className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3"
          onChange={(next) =>
            onUpdateConfig({
              [fieldKey]: field.type === "number" ? Number(next) : next,
            })
          }
          placeholder={fieldKey === "path" ? "Type or paste file/directory path" : undefined}
          type={field.type === "number" ? "number" : "text"}
          value={String(currentValue)}
        />
        {browseMode && (
          <button
            type="button"
            className="shrink-0 rounded-2xl border border-stone-300 bg-white px-3 text-sm text-stone-600 hover:bg-stone-50"
            title="Browse filesystem"
            onClick={() => void handleBrowseClick()}
          >
            ...
          </button>
        )}
      </div>
      {browseOpen && browseMode && (
        <FileBrowserModal
          mode={browseMode === "directory" ? "directory_browser" : "file_browser"}
          initialPath={modalInitialPath(browseMode, String(currentValue ?? ""))}
          onSelect={(selectedPath) => {
            applySelectedPath([selectedPath]);
            setBrowseOpen(false);
          }}
          onCancel={() => setBrowseOpen(false)}
        />
      )}
    </label>
  );
}

function ConfigField({
  fieldKey,
  field,
  currentValue,
  onUpdateConfig,
}: {
  fieldKey: string;
  field: Record<string, unknown>;
  currentValue: unknown;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  if (Array.isArray(field.enum)) {
    return (
      <EnumField
        fieldKey={fieldKey}
        field={field}
        currentValue={currentValue}
        onUpdateConfig={onUpdateConfig}
      />
    );
  }
  return (
    <ScalarField
      fieldKey={fieldKey}
      field={field}
      currentValue={currentValue}
      onUpdateConfig={onUpdateConfig}
    />
  );
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

export function ConfigPanel({
  selectedNode,
  schema,
  onUpdateConfig,
}: {
  selectedNode: WorkflowNode | null;
  schema?: BlockSchemaResponse;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const params = ((selectedNode?.config.params as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;
  const ordered = orderedConfigEntries(schema, selectedNode);

  if (!selectedNode || !schema) {
    return <div className="text-sm text-stone-500">Select a node to edit its settings.</div>;
  }

  if (isCodeBlockConfigTarget(selectedNode, schema)) {
    return <CodeBlockConfigEditor onUpdateConfig={onUpdateConfig} params={params} />;
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

  return (
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
      {!hasCoreTypeField && formatSelector ? (
        <div className="mb-4 max-w-2xl">{formatSelector}</div>
      ) : null}
      <div className={hasCoreTypeField ? "grid max-w-2xl gap-4" : "grid gap-4 md:grid-cols-2"}>
        {ordered.map(([key, value]) => {
          const currentValue = params[key] ?? value.default ?? "";
          return (
            <div key={key} className="contents">
              <ConfigField
                fieldKey={key}
                field={value}
                currentValue={currentValue}
                onUpdateConfig={onUpdateConfig}
              />
              {hasCoreTypeField && key === "core_type" && formatSelector}
            </div>
          );
        })}
      </div>
    </div>
  );
}
