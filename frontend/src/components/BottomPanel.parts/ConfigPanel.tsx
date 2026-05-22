import { api } from "../../lib/api";
import type { BlockSchemaResponse, WorkflowNode } from "../../types/api";
import { type PortRow, PortEditorTable } from "../PortEditorTable";

import { CaretPreservingTextInput } from "./CaretPreservingTextInput";
import { CodeBlockConfigEditor } from "./CodeBlockConfigEditor";
import { FormatCapabilityConfig } from "./FormatCapabilityConfig";
import { isCodeBlockConfigTarget } from "./codeBlockPorts";

type BrowseMode = "file" | "directory" | null;

function browseModeFor(uiWidget: string | undefined): BrowseMode {
  if (uiWidget === "file_browser") return "file";
  if (uiWidget === "directory_browser") return "directory";
  return null;
}

async function runBrowseDialog(
  browseMode: NonNullable<BrowseMode>,
  current: string,
  schemaTypeRaw: unknown,
  onUpdateConfig: (patch: Record<string, unknown>) => void,
  key: string,
) {
  // Mirror BlockNode's inline browse pattern (#484): use the
  // backend's native dialog so the user gets their OS file
  // picker. Failure surfaces in console; the text field
  // remains usable as the manual fallback.
  let initialDir: string | undefined;
  if (current) {
    const sep = current.includes("\\") ? "\\" : "/";
    const parts = current.split(sep);
    if (browseMode === "file" && parts.length > 1 && parts[parts.length - 1].includes(".")) {
      initialDir = parts.slice(0, -1).join(sep);
    } else {
      initialDir = current;
    }
  }
  try {
    const result = await api.openNativeDialog(browseMode, initialDir);
    if (result.paths.length > 0) {
      const supportsArray = Array.isArray(schemaTypeRaw)
        ? schemaTypeRaw.includes("array")
        : schemaTypeRaw === "array";
      onUpdateConfig({
        [key]: supportsArray && result.paths.length > 1 ? result.paths : result.paths[0],
      });
    }
  } catch (err) {
    console.error("BottomPanel: native file dialog failed", err);
  }
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
        onChange={(event) => onUpdateConfig({ [fieldKey]: event.target.value })}
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
  const uiWidget = field.ui_widget as string | undefined;
  const browseMode = browseModeFor(uiWidget);
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
            onClick={() =>
              runBrowseDialog(
                browseMode,
                String(currentValue ?? ""),
                field.type,
                onUpdateConfig,
                fieldKey,
              )
            }
          >
            ...
          </button>
        )}
      </div>
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
    return (
      <div className="text-sm text-stone-500">
        Select a node to edit its JSON-schema-driven configuration.
      </div>
    );
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
      {formatCapabilities.length > 0 ? (
        <div className="mb-4 max-w-2xl">
          <FormatCapabilityConfig
            capabilities={formatCapabilities}
            onChange={(capabilityId) => onUpdateConfig({ capability_id: capabilityId })}
            value={params.capability_id}
          />
        </div>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {ordered.map(([key, value]) => {
          const currentValue = params[key] ?? value.default ?? "";
          return (
            <ConfigField
              key={key}
              fieldKey={key}
              field={value}
              currentValue={currentValue}
              onUpdateConfig={onUpdateConfig}
            />
          );
        })}
      </div>
    </div>
  );
}
