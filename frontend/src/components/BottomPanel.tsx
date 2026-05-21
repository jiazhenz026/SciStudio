import { GitBranch, Pin, PinOff, Plus, Trash2 } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api } from "../lib/api";
import type { BlockSchemaResponse, FormatCapabilityResponse, LogEntry, WorkflowNode } from "../types/api";
import type { BottomTab } from "../types/ui";
import { TerminalTabs } from "./AIChat/TerminalTabs";
import { GitTab } from "./Git/GitTab";
import { LineageTab } from "./Lineage/LineageTab";
import { type PortRow, PortEditorTable } from "./PortEditorTable";

interface BottomPanelProps {
  activeTab: BottomTab;
  selectedNode: WorkflowNode | null;
  selectedSchema?: BlockSchemaResponse;
  logEntries: LogEntry[];
  onTabChange: (tab: BottomTab) => void;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  // Unread counter for the Logs tab badge. Defaults to 0; the badge
  // renders only when > 0. (The Problems tab was removed — block errors
  // are already represented by an inline badge on the BlockNode itself
  // and by error-level rows in the Logs panel.)
  unreadLogsCount?: number;
  /**
   * When true, the bottom panel is "pinned" — App.tsx will skip the
   * canvas-pane-click auto-collapse so AI Chat sessions stay open. The
   * pin button in the tab strip toggles this via ``onTogglePin``.
   */
  pinned?: boolean;
  onTogglePin?: () => void;
}

// Tab labels: emoji + text for most tabs (matches existing visual style);
// Git uses the Lucide `GitBranch` icon for a sharper, more on-brand glyph
// rather than the U+1F500 shuffle emoji which reads as "random" and
// renders inconsistently across OS font sets.
const TAB_LABELS: Record<BottomTab, ReactNode> = {
  ai: "\u{1F4AC} AI Chat",
  config: "\u{1F4CB} Config",
  logs: "\u{1F4DC} Logs",
  // ADR-038 §3.8 — Lineage tab promoted to a first-class entry; replaces
  // the prior Jobs placeholder which is removed entirely.
  lineage: "\u{1F517} Lineage",
  // ADR-039 §3.5 (#972) — Git versioning surface moved out of the top
  // Toolbar into a dedicated bottom-panel tab so the commit history /
  // branch graph / merge flows are reachable without overflowing the
  // toolbar on narrow viewports.
  git: (
    <span className="inline-flex items-center gap-1.5">
      <GitBranch className="h-4 w-4" aria-hidden="true" />
      Git
    </span>
  ),
};

// Problems was removed: it duplicated the block_error rows already in Logs
// (filterable via LogViewer's level selector) plus the inline error badge
// rendered on the BlockNode itself by WorkflowCanvas.
// ADR-038 §3.8 — Jobs tab removed (subsumed by Lineage).
// ADR-039 §3.5 (#972) — Git tab added.
const ALL_TABS: BottomTab[] = ["ai", "config", "logs", "lineage", "git"];

// Controlled text input that preserves caret position across re-renders (#710).
//
// The standard React controlled-input pattern resets the browser caret to
// the end of the value whenever the `value` prop is replaced by a non-
// synchronous round-trip (e.g. onChange -> Zustand -> next render). This
// component captures selectionStart/selectionEnd on each change and restores
// them in a layout effect after the value prop has been applied.
//
// Audit follow-up (#710): only restore when the re-render originated from
// this input's own onChange. Previously selectionRef stayed live across
// renders, which meant any unrelated re-render while the field stayed
// focused (e.g. user moves the caret with mouse/arrow keys, then a sibling
// state update fires) would force the caret back to the stale post-edit
// position. We now store the pending selection only between onChange and
// the next layout effect, then null it out so subsequent renders are
// no-ops unless another onChange refills the ref. The activeElement guard
// still ensures we never steal selection from another input (the canvas
// BlockNode renders the same field, bound to the same store).
function CaretPreservingTextInput({
  value,
  onChange,
  type,
  className,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  type: "text" | "number";
  className?: string;
  placeholder?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(
    null,
  );
  useLayoutEffect(() => {
    const pending = pendingSelectionRef.current;
    const el = inputRef.current;
    if (pending && el && document.activeElement === el) {
      try {
        el.setSelectionRange(pending.start, pending.end);
      } catch {
        // setSelectionRange is not supported on type=number; ignore.
      }
    }
    // Always clear after attempting restore so the next render does
    // nothing unless another onChange refills the ref.
    pendingSelectionRef.current = null;
  });
  return (
    <input
      ref={inputRef}
      className={className}
      onChange={(event) => {
        // type=number does not expose selectionStart/selectionEnd in most
        // browsers; values come back as null which we coalesce to 0. The
        // activeElement guard above still gates the restore, so unfocused
        // mirrors do not steal selection.
        pendingSelectionRef.current = {
          start: event.target.selectionStart ?? 0,
          end: event.target.selectionEnd ?? 0,
        };
        onChange(event.target.value);
      }}
      placeholder={placeholder}
      type={type}
      value={value}
    />
  );
}

function capabilityLabel(capability: FormatCapabilityResponse): string {
  const extensions = capability.extensions.join(", ");
  return extensions ? `${capability.label} (${extensions})` : capability.label;
}

function selectedCapability(
  capabilities: FormatCapabilityResponse[],
  capabilityId: unknown,
): FormatCapabilityResponse | undefined {
  if (typeof capabilityId === "string") {
    const selected = capabilities.find((capability) => capability.id === capabilityId);
    if (selected) return selected;
  }
  if (capabilities.length === 1) return capabilities[0];
  return capabilities.find((capability) => capability.is_default);
}

function capabilityWarnings(
  capabilities: FormatCapabilityResponse[],
  capability?: FormatCapabilityResponse,
): string[] {
  const warnings: string[] = [];
  if (capabilities.length > 1 && !capability) {
    warnings.push("Multiple backend capabilities match this block; choose one to persist a stable capability_id.");
  }
  if (capability?.direction === "save" && capability.metadata_fidelity.level === "pixel_only") {
    warnings.push("This saver is payload-only; typed metadata may not be written.");
  }
  if (capability?.migration_scaffold) {
    warnings.push("This is a synthesized legacy capability kept for migration compatibility.");
  }
  return warnings;
}

function FormatCapabilityConfig({
  capabilities,
  value,
  onChange,
}: {
  capabilities: FormatCapabilityResponse[];
  value: unknown;
  onChange: (capabilityId: string | null) => void;
}) {
  if (capabilities.length === 0) return null;
  const capability = selectedCapability(capabilities, value);
  const warnings = capabilityWarnings(capabilities, capability);
  const selectValue = typeof value === "string" ? value : (capability?.id ?? "");

  return (
    <div className="grid gap-2 text-sm">
      <label className="grid gap-2">
        <span className="font-medium text-ink">Format</span>
        <select
          className="w-full rounded-2xl border border-stone-300 bg-white px-4 py-3"
          disabled={capabilities.length === 1}
          onChange={(event) => onChange(event.target.value || null)}
          value={selectValue}
          title={capability?.id}
        >
          {capabilities.length > 1 ? <option value="">Select a format capability...</option> : null}
          {capabilities.map((option) => (
            <option key={option.id} value={option.id}>
              {capabilityLabel(option)}
            </option>
          ))}
        </select>
      </label>
      {capability ? (
        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-600">
          {/* Verbose ``capability.id`` (e.g. ``scistudio-blocks-imaging.image.tiff.load``)
              is exposed via the select's ``title`` tooltip above. Keep only the
              structural triple here so the panel does not duplicate the dropdown
              label in a long-form id row. */}
          <div>
            {capability.data_type} / {capability.format_id} / {capability.metadata_fidelity.level}
          </div>
        </div>
      ) : null}
      {warnings.map((warning) => (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" key={warning}>
          {warning}
        </div>
      ))}
    </div>
  );
}

type CodeBlockPortDirection = "input" | "output";

interface CodeBlockPortConfig {
  name: string;
  direction: CodeBlockPortDirection;
  data_type: string;
  extension: string;
  capability_id?: string | null;
  required: boolean;
  exchange_folder: string;
}

const CODEBLOCK_DATA_TYPES = ["DataObject", "Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCodeBlockConfigTarget(selectedNode: WorkflowNode | null, schema?: BlockSchemaResponse): boolean {
  const tokens = [selectedNode?.block_type, schema?.type_name, schema?.name]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.toLowerCase().replace(/[\s._-]+/g, ""));

  return tokens.some((token) => token === "codeblock" || token.endsWith("codeblock"));
}

function codeBlockFolder(direction: CodeBlockPortDirection, name: string): string {
  const safeName = name.trim() || "port";
  return `${direction}s/${safeName}/`;
}

function nextCodeBlockPortName(direction: CodeBlockPortDirection, ports: CodeBlockPortConfig[]): string {
  const existing = new Set(ports.map((port) => port.name));
  let index = ports.length + 1;
  let name = `${direction}_${index}`;
  while (existing.has(name)) {
    index += 1;
    name = `${direction}_${index}`;
  }
  return name;
}

function normalizeCodeBlockPort(
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
    capability_id: row.capability_id == null ? "" : String(row.capability_id),
    required: typeof row.required === "boolean" ? row.required : true,
    exchange_folder: exchangeFolder,
  };
}

function codeBlockPorts(params: Record<string, unknown>, key: "inputs" | "outputs", direction: CodeBlockPortDirection) {
  const rawPorts = Array.isArray(params[key]) ? params[key] : [];
  return rawPorts.map((port, index) => normalizeCodeBlockPort(port, direction, index));
}

function persistCodeBlockPort(port: CodeBlockPortConfig, direction: CodeBlockPortDirection): Record<string, unknown> {
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

function CodeBlockEnvironmentEditor({
  value,
  onUpdate,
}: {
  value: unknown;
  onUpdate: (next: Record<string, string>) => void;
}) {
  const variables = isRecord(value) ? Object.entries(value).map(([key, envValue]) => [key, String(envValue)] as const) : [];

  const updateEntry = (index: number, nextKey: string, nextValue: string) => {
    const currentKey = variables[index]?.[0] ?? "";
    const duplicateKey = nextKey !== currentKey && variables.some(([key], rowIndex) => rowIndex !== index && key === nextKey);
    if (duplicateKey) {
      onUpdate(Object.fromEntries(variables));
      return;
    }

    const nextEntries = variables.map(([key, envValue], rowIndex) =>
      rowIndex === index ? ([nextKey, nextValue] as const) : ([key, envValue] as const),
    );
    onUpdate(Object.fromEntries(nextEntries));
  };

  const addEntry = () => {
    let index = variables.length + 1;
    let key = `VAR_${index}`;
    const existing = new Set(variables.map(([name]) => name));
    while (existing.has(key)) {
      index += 1;
      key = `VAR_${index}`;
    }
    onUpdate({ ...Object.fromEntries(variables), [key]: "" });
  };

  const removeEntry = (index: number) => {
    onUpdate(Object.fromEntries(variables.filter((_, rowIndex) => rowIndex !== index)));
  };

  return (
    <section className="grid gap-3 border-t border-stone-200 pt-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">Environment variables</h3>
        <button
          className="inline-flex items-center gap-2 rounded-full border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-700"
          onClick={addEntry}
          type="button"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add variable
        </button>
      </div>
      {variables.length ? (
        <div className="grid gap-2">
          {variables.map(([key, envValue], index) => (
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" key={`${key}-${index}`}>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-stone-700">Name</span>
                <CaretPreservingTextInput
                  className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                  onChange={(next) => updateEntry(index, next, envValue)}
                  type="text"
                  value={key}
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-stone-700">Value</span>
                <CaretPreservingTextInput
                  className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                  onChange={(next) => updateEntry(index, key, next)}
                  type="text"
                  value={envValue}
                />
              </label>
              <button
                aria-label={`Remove environment variable ${key || index + 1}`}
                className="self-end rounded-full border border-stone-300 bg-white p-3 text-stone-600"
                onClick={() => removeEntry(index)}
                type="button"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-stone-500">No environment variables configured.</p>
      )}
    </section>
  );
}

function CodeBlockPortTable({
  direction,
  ports,
  onChange,
}: {
  direction: CodeBlockPortDirection;
  ports: CodeBlockPortConfig[];
  onChange: (next: CodeBlockPortConfig[]) => void;
}) {
  const label = direction === "input" ? "Declared inputs" : "Declared outputs";

  const updatePort = (index: number, patch: Partial<CodeBlockPortConfig>) => {
    onChange(
      ports.map((port, rowIndex) => {
        if (rowIndex !== index) return port;
        const next = { ...port, ...patch };
        if (patch.name && !patch.exchange_folder) {
          next.exchange_folder = codeBlockFolder(direction, patch.name);
        }
        return next;
      }),
    );
  };

  const addPort = () => {
    const nextName = nextCodeBlockPortName(direction, ports);
    onChange([
      ...ports,
      {
        name: nextName,
        direction,
        data_type: "DataObject",
        extension: ".txt",
        capability_id: "",
        required: true,
        exchange_folder: codeBlockFolder(direction, nextName),
      },
    ]);
  };

  const removePort = (index: number) => {
    onChange(ports.filter((_, rowIndex) => rowIndex !== index));
  };

  return (
    <section className="grid gap-3 border-t border-stone-200 pt-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">{label}</h3>
        <button
          className="inline-flex items-center gap-2 rounded-full border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-700"
          onClick={addPort}
          type="button"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add {direction}
        </button>
      </div>
      {ports.length ? (
        <div className="grid gap-3">
          {ports.map((port, index) => (
            <div className="grid gap-3 rounded-2xl border border-stone-200 bg-white/70 p-3" key={`${direction}-${index}`}>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.75fr)]">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-stone-700">Name</span>
                  <CaretPreservingTextInput
                    className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                    onChange={(next) => updatePort(index, { name: next })}
                    type="text"
                    value={port.name}
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-stone-700">Data type</span>
                  <select
                    className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
                    onChange={(event) => updatePort(index, { data_type: event.target.value })}
                    value={port.data_type}
                  >
                    {Array.from(new Set([port.data_type, ...CODEBLOCK_DATA_TYPES])).map((typeName) => (
                      <option key={typeName} value={typeName}>
                        {typeName}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-stone-700">Extension</span>
                  <CaretPreservingTextInput
                    className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                    onChange={(next) => updatePort(index, { extension: next })}
                    type="text"
                    value={port.extension}
                  />
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-stone-700">Capability ID</span>
                  <CaretPreservingTextInput
                    className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                    onChange={(next) => updatePort(index, { capability_id: next })}
                    type="text"
                    value={port.capability_id ?? ""}
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-stone-700">Exchange folder</span>
                  <CaretPreservingTextInput
                    className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                    onChange={(next) => updatePort(index, { exchange_folder: next })}
                    type="text"
                    value={port.exchange_folder}
                  />
                </label>
                <label className="flex items-center gap-2 self-end rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-700">
                  <input
                    checked={port.required}
                    className="h-4 w-4"
                    onChange={(event) => updatePort(index, { required: event.target.checked })}
                    type="checkbox"
                  />
                  Required
                </label>
                <button
                  aria-label={`Remove ${direction} ${port.name || index + 1}`}
                  className="self-end rounded-full border border-stone-300 bg-white p-3 text-stone-600"
                  onClick={() => removePort(index)}
                  type="button"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <p className="text-xs text-stone-500">
                {direction === "input" ? "Read from" : "Save into"} <code>{port.exchange_folder}</code>
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-stone-500">No {direction} ports declared.</p>
      )}
    </section>
  );
}

function CodeBlockConfigEditor({
  params,
  onUpdateConfig,
}: {
  params: Record<string, unknown>;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const inputs = codeBlockPorts(params, "inputs", "input");
  const outputs = codeBlockPorts(params, "outputs", "output");

  const updatePorts = (key: "inputs" | "outputs", direction: CodeBlockPortDirection, ports: CodeBlockPortConfig[]) => {
    onUpdateConfig({ [key]: ports.map((port) => persistCodeBlockPort(port, direction)) });
  };

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="grid gap-2 text-sm md:col-span-2">
          <span className="font-medium text-ink">Script path</span>
          <CaretPreservingTextInput
            className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(next) => onUpdateConfig({ script_path: next })}
            placeholder="scripts/analyze.py"
            type="text"
            value={String(params.script_path ?? "")}
          />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Interpreter mode</span>
          <select
            className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(event) => onUpdateConfig({ interpreter_mode: event.target.value })}
            value={String(params.interpreter_mode ?? "auto")}
          >
            <option value="auto">auto</option>
            <option value="existing">existing</option>
          </select>
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Interpreter path</span>
          <CaretPreservingTextInput
            className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(next) => onUpdateConfig({ interpreter_path: next })}
            placeholder="python"
            type="text"
            value={String(params.interpreter_path ?? "")}
          />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Working directory</span>
          <CaretPreservingTextInput
            className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(next) => onUpdateConfig({ working_directory: next })}
            type="text"
            value={String(params.working_directory ?? ".")}
          />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Exchange root</span>
          <CaretPreservingTextInput
            className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(next) => onUpdateConfig({ exchange_root: next })}
            type="text"
            value={String(params.exchange_root ?? "exchange")}
          />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Timeout seconds</span>
          <CaretPreservingTextInput
            className="min-w-0 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(next) => onUpdateConfig({ timeout_seconds: next === "" ? null : Number(next) })}
            type="number"
            value={params.timeout_seconds == null ? "" : String(params.timeout_seconds)}
          />
        </label>
      </div>

      <CodeBlockEnvironmentEditor
        onUpdate={(next) => onUpdateConfig({ environment_variables: next })}
        value={params.environment_variables}
      />
      <CodeBlockPortTable
        direction="input"
        onChange={(next) => updatePorts("inputs", "input", next)}
        ports={inputs}
      />
      <CodeBlockPortTable
        direction="output"
        onChange={(next) => updatePorts("outputs", "output", next)}
        ports={outputs}
      />
    </div>
  );
}

function ConfigPanel({
  selectedNode,
  schema,
  onUpdateConfig,
}: {
  selectedNode: WorkflowNode | null;
  schema?: BlockSchemaResponse;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const params = ((selectedNode?.config.params as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const properties = schema?.config_schema.properties ?? {};
  const ordered = Object.entries(properties)
    .filter(([key, value]) => {
      // For io_block, hide "direction" — it is already determined by whether
      // the user dragged a Load Block or Save Block from the palette.
      if ((schema?.direction || selectedNode?.block_type === "io_block") && key === "direction") return false;
      if (key === "capability_id") return false;
      // Skip port_editor fields — rendered separately as PortEditorTable below.
      if ((value as Record<string, unknown>).ui_widget === "port_editor") return false;
      return true;
    })
    .sort(([, left], [, right]) => {
      return Number(left.ui_priority ?? 99) - Number(right.ui_priority ?? 99);
    });

  const isVariadicInputs = schema?.variadic_inputs === true;
  const isVariadicOutputs = schema?.variadic_outputs === true;
  const inputPorts = Array.isArray(params["input_ports"]) ? (params["input_ports"] as PortRow[]) : [];
  const outputPorts = Array.isArray(params["output_ports"]) ? (params["output_ports"] as PortRow[]) : [];
  const typeHierarchy = schema?.type_hierarchy ?? [];
  const allowedInputTypes = schema?.allowed_input_types ?? [];
  const allowedOutputTypes = schema?.allowed_output_types ?? [];
  const formatCapabilities = schema?.format_capabilities ?? [];

  if (!selectedNode || !schema) {
    return <div className="text-sm text-stone-500">Select a node to edit its JSON-schema-driven configuration.</div>;
  }

  if (isCodeBlockConfigTarget(selectedNode, schema)) {
    return <CodeBlockConfigEditor onUpdateConfig={onUpdateConfig} params={params} />;
  }

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
        if (Array.isArray(value.enum)) {
          return (
            <label className="grid gap-2 text-sm" key={key}>
              <span className="font-medium text-ink">{String(value.title ?? key)}</span>
              <select
                className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
                onChange={(event) => onUpdateConfig({ [key]: event.target.value })}
                value={String(currentValue)}
              >
                {value.enum.map((option) => (
                  <option key={String(option)} value={String(option)}>
                    {String(option)}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        const uiWidget = (value as Record<string, unknown>).ui_widget as string | undefined;
        const browseMode: "file" | "directory" | null =
          uiWidget === "file_browser"
            ? "file"
            : uiWidget === "directory_browser"
              ? "directory"
              : null;
        return (
          <label className="grid gap-2 text-sm" key={key}>
            <span className="font-medium text-ink">{String(value.title ?? key)}</span>
            <div className="flex w-full min-w-0 items-stretch gap-2">
              <CaretPreservingTextInput
                className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3"
                onChange={(next) =>
                  onUpdateConfig({
                    [key]: value.type === "number" ? Number(next) : next,
                  })
                }
                placeholder={key === "path" ? "Type or paste file/directory path" : undefined}
                type={value.type === "number" ? "number" : "text"}
                value={String(currentValue)}
              />
              {browseMode && (
                <button
                  type="button"
                  className="shrink-0 rounded-2xl border border-stone-300 bg-white px-3 text-sm text-stone-600 hover:bg-stone-50"
                  title="Browse filesystem"
                  onClick={async () => {
                    // Mirror BlockNode's inline browse pattern (#484): use the
                    // backend's native dialog so the user gets their OS file
                    // picker. Failure surfaces in console; the text field
                    // remains usable as the manual fallback.
                    const current = String(currentValue ?? "");
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
                        const schemaType = (value as Record<string, unknown>).type;
                        const supportsArray = Array.isArray(schemaType)
                          ? schemaType.includes("array")
                          : schemaType === "array";
                        onUpdateConfig({
                          [key]:
                            supportsArray && result.paths.length > 1
                              ? result.paths
                              : result.paths[0],
                        });
                      }
                    } catch (err) {
                      // eslint-disable-next-line no-console
                      console.error("BottomPanel: native file dialog failed", err);
                    }
                  }}
                >
                  ...
                </button>
              )}
            </div>
          </label>
        );
      })}
      </div>
    </div>
  );
}

function LogViewer({ entries }: { entries: LogEntry[] }) {
  const [level, setLevel] = useState("all");
  const filtered = useMemo(() => {
    return entries.filter((entry) => level === "all" || entry.level === level);
  }, [entries, level]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center gap-3">
        <select className="rounded-full border border-stone-300 bg-white px-3 py-2 text-sm" onChange={(event) => setLevel(event.target.value)} value={level}>
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="error">Error</option>
        </select>
      </div>
      <div className="flex-1 overflow-auto rounded-[1.4rem] border border-stone-200 bg-stone-950 p-4">
        {filtered.length ? (
          filtered.map((entry, index) => (
            <div className="border-b border-stone-800 py-2 text-sm text-stone-100" key={`${entry.timestamp}-${index}`}>
              <p className="text-[11px] uppercase tracking-[0.3em] text-stone-500">
                {entry.level} · {entry.workflow_id ?? "workflow"} · {entry.block_id ?? "system"}
              </p>
              <p className="mt-1">{entry.message}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-stone-500">No logs yet.</p>
        )}
      </div>
    </div>
  );
}

function PlaceholderTab() {
  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-stone-400">Coming in Phase 8.5</p>
    </div>
  );
}

export function BottomPanel({
  activeTab,
  selectedNode,
  selectedSchema,
  logEntries,
  onTabChange,
  onUpdateConfig,
  unreadLogsCount = 0,
  pinned = false,
  onTogglePin,
}: BottomPanelProps) {
  const badgeFor = (tab: BottomTab): number => {
    if (tab === activeTab) return 0;
    if (tab === "logs") return unreadLogsCount;
    return 0;
  };
  const formatBadge = (n: number): string => (n > 99 ? "99+" : String(n));

  // ADR-039 §3.5 — MergeFlow modal is mounted at App.tsx level (NOT
  // here) so it survives BOTH bottom-tab switches AND project close
  // (Codex round-2 P1 on PR #974, follow-up issue #975). BottomPanel
  // itself unmounts when `currentProject` becomes null, which would
  // otherwise bypass MergeFlow's mid-conflict close-guard. See
  // App.tsx for the current mount.

  return (
    <section className="flex h-full flex-col overflow-hidden bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(238,231,219,0.98))]">
      <div className="flex items-center gap-3 border-b border-stone-200 px-4 py-3">
        <div className="flex flex-1 gap-2">
          {ALL_TABS.map((tab) => {
            const badge = badgeFor(tab);
            return (
              <button
                className={`rounded-full px-4 py-2 text-sm font-medium ${activeTab === tab ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={tab}
                onClick={() => onTabChange(tab)}
                type="button"
              >
                {TAB_LABELS[tab]}
                {badge > 0 ? (
                  <span
                    className="ml-2 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white"
                    data-testid={`unread-badge-${tab}`}
                  >
                    {formatBadge(badge)}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
        {onTogglePin ? (
          <button
            aria-label={pinned ? "Unpin bottom panel" : "Pin bottom panel (disable canvas-click auto-collapse)"}
            aria-pressed={pinned}
            className={`inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
              pinned ? "bg-ember/15 text-ember" : "bg-white text-stone-500 hover:bg-stone-100"
            }`}
            data-testid="bottom-panel-pin-toggle"
            onClick={onTogglePin}
            title={pinned ? "Pinned — clicks on canvas won't fold the panel" : "Pin panel — clicks on canvas won't fold it"}
            type="button"
          >
            {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
          </button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 scrollbar-thin">
        {/* TerminalTabs must stay MOUNTED across bottom-panel tab switches
            so the PTY subprocess survives (unmount fires the WS cleanup
            hook which kills the child process tree). Hide via CSS when
            another tab is active.

            Hotfix #977: the inner white-card frame was removed so the
            active-tab body fills the available space without a nested
            scroll context. The lineage tab (ADR-038 §3.8) and git tab
            (ADR-039 §3.5, #972) both render inside this flat container. */}
        <div className={`h-full ${activeTab === "ai" ? "" : "hidden"}`}>
          <TerminalTabs />
        </div>
        {activeTab === "config" ? (
          <ConfigPanel onUpdateConfig={onUpdateConfig} schema={selectedSchema} selectedNode={selectedNode} />
        ) : activeTab === "logs" ? (
          <LogViewer entries={logEntries} />
        ) : activeTab === "lineage" ? (
          // ADR-038 §3.8 — D38-2.4b skeleton mounts <LineageTab/>.
          // The root component renders a non-throwing placeholder until
          // D38-2.4c IMPL fills the two-pane runs-list + run-detail view.
          <LineageTab />
        ) : activeTab === "git" ? (
          // ADR-039 §3.5 (#972) — Git tab. GitTab owns its own modal
          // (CommitDialog) so it unmounts when the user switches away
          // from this tab. MergeFlow is mounted separately below (its
          // conflict-state close guard must survive bottom-tab
          // switches; Codex P1 on PR #974).
          <GitTab />
        ) : activeTab !== "ai" ? (
          <PlaceholderTab />
        ) : null}
      </div>
    </section>
  );
}
