import type { BlockSchemaResponse, WorkflowNode } from "../../types/api";

export type CodeBlockPortDirection = "input" | "output";

export interface CodeBlockPortConfig {
  name: string;
  direction: CodeBlockPortDirection;
  data_type: string;
  extension: string;
  capability_id?: string | null;
  required: boolean;
  exchange_folder: string;
}

export const CODEBLOCK_DATA_TYPES = [
  "DataObject",
  "Array",
  "DataFrame",
  "Series",
  "Text",
  "Artifact",
  "CompositeData",
];

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isCodeBlockConfigTarget(
  selectedNode: WorkflowNode | null,
  schema?: BlockSchemaResponse,
): boolean {
  const tokens = [selectedNode?.block_type, schema?.type_name, schema?.name]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.toLowerCase().replace(/[\s._-]+/g, ""));

  return tokens.some((token) => token === "codeblock" || token.endsWith("codeblock"));
}

export function codeBlockFolder(direction: CodeBlockPortDirection, name: string): string {
  const safeName = name.trim() || "port";
  return `${direction}s/${safeName}/`;
}

export function nextCodeBlockPortName(
  direction: CodeBlockPortDirection,
  ports: CodeBlockPortConfig[],
): string {
  const existing = new Set(ports.map((port) => port.name));
  let index = ports.length + 1;
  let name = `${direction}_${index}`;
  while (existing.has(name)) {
    index += 1;
    name = `${direction}_${index}`;
  }
  return name;
}

export function normalizeCodeBlockPort(
  value: unknown,
  direction: CodeBlockPortDirection,
  index: number,
): CodeBlockPortConfig {
  const row = isRecord(value) ? value : {};
  const name = String(row.name ?? `${direction}_${index + 1}`);
  const exchangeFolder = String(row.exchange_folder ?? codeBlockFolder(direction, name));

  return {
    name,
    direction,
    data_type: String(row.data_type ?? "DataObject"),
    extension: String(row.extension ?? ".txt"),
    capability_id:
      row.capability_id === null || row.capability_id === undefined
        ? ""
        : String(row.capability_id),
    required: typeof row.required === "boolean" ? row.required : true,
    exchange_folder: exchangeFolder,
  };
}

export function codeBlockPorts(
  params: Record<string, unknown>,
  key: "inputs" | "outputs",
  direction: CodeBlockPortDirection,
) {
  const rawPorts = Array.isArray(params[key]) ? params[key] : [];
  return rawPorts.map((port, index) => normalizeCodeBlockPort(port, direction, index));
}

export function persistCodeBlockPort(
  port: CodeBlockPortConfig,
  direction: CodeBlockPortDirection,
): Record<string, unknown> {
  const name = port.name.trim();
  const exchangeFolder = port.exchange_folder.trim() || codeBlockFolder(direction, name);

  return {
    name,
    direction,
    data_type: port.data_type.trim(),
    extension: port.extension.trim(),
    capability_id: port.capability_id?.trim() ? port.capability_id.trim() : null,
    required: port.required,
    exchange_folder: exchangeFolder,
  };
}

/**
 * Hotfix 2026-05-23 (#1324 partial cover) — Code Block stores its declared v2
 * ports under ``params.inputs`` / ``params.outputs`` (full
 * :class:`CodeBlockPortConfig` shape used by the runtime exchange), while the
 * canvas + variadic add/remove buttons drive ``params.input_ports`` /
 * ``params.output_ports`` (the ``{name, types}`` shape every other variadic
 * block uses). These two lists were edited independently, so adding a port on
 * the canvas never appeared in the BottomPanel config editor, and vice versa.
 *
 * The helpers below project between the two shapes so callers can emit a
 * single patch that keeps both lists in sync. They are intentionally pure and
 * unaware of the store — call them inside ``onUpdateConfig`` callbacks.
 *
 * Layout still differs (the BottomPanel uses the richer CodeBlockPortTable
 * with extension / capability / exchange-folder rows). Aligning the layout
 * with Fiji's PortEditorTable is tracked separately under issue #1324.
 */
export function variadicEntryFromCodeBlockPort(port: CodeBlockPortConfig): {
  name: string;
  types: string[];
} {
  return { name: port.name.trim(), types: [port.data_type.trim() || "DataObject"] };
}

export function codeBlockPortFromVariadicEntry(
  entry: { name: string; types?: string[] },
  direction: CodeBlockPortDirection,
  existing?: CodeBlockPortConfig,
): CodeBlockPortConfig {
  const dataType = entry.types?.[0]?.trim() || existing?.data_type || "DataObject";
  return {
    name: entry.name,
    direction,
    data_type: dataType,
    extension: existing?.extension ?? ".txt",
    capability_id: existing?.capability_id ?? "",
    required: existing?.required ?? true,
    exchange_folder: existing?.exchange_folder ?? codeBlockFolder(direction, entry.name),
  };
}
