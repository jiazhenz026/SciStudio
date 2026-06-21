import { Plus, Trash2 } from "lucide-react";

import { CaretPreservingTextInput } from "./CaretPreservingTextInput";
// Reuse the generic scalar/browse field so script_path gets the exact same
// file-browser button as every other block. ConfigField lives in its own
// module so neither ConfigPanel nor this editor import each other indirectly.
import { ConfigField } from "./ConfigField";
// Same capability picker the AppBlock/Fiji port editor uses (#1324): lists
// savers (input ports) / loaders (output ports) for the (direction, type,
// extension) tuple instead of a free-text capability_id.
import { CapabilityDropdown } from "../PortEditor/CapabilityDropdown";
import type { TypeHierarchyEntry } from "../../types/api";
import {
  CODEBLOCK_DATA_TYPES,
  type CodeBlockPortConfig,
  type CodeBlockPortDirection,
  codeBlockFolder,
  codeBlockPorts,
  isRecord,
  nextCodeBlockPortName,
  persistCodeBlockPort,
  variadicEntryFromCodeBlockPort,
} from "./codeBlockPorts";

function CodeBlockEnvironmentEditor({
  value,
  onUpdate,
}: {
  value: unknown;
  onUpdate: (next: Record<string, string>) => void;
}) {
  const variables = isRecord(value)
    ? Object.entries(value).map(([key, envValue]) => [key, String(envValue)] as const)
    : [];

  const updateEntry = (index: number, nextKey: string, nextValue: string) => {
    const currentKey = variables[index]?.[0] ?? "";
    const duplicateKey =
      nextKey !== currentKey &&
      variables.some(([key], rowIndex) => rowIndex !== index && key === nextKey);
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
            <div
              className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              key={`${key}-${index}`}
            >
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
  typeHierarchy,
}: {
  direction: CodeBlockPortDirection;
  ports: CodeBlockPortConfig[];
  onChange: (next: CodeBlockPortConfig[]) => void;
  typeHierarchy: TypeHierarchyEntry[];
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
        // #1366 parity: changing the type or extension invalidates a pinned
        // capability_id, so drop it and let CapabilityDropdown re-resolve.
        if (("data_type" in patch || "extension" in patch) && !("capability_id" in patch)) {
          next.capability_id = "";
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
            <div
              className="grid gap-3 rounded-2xl border border-stone-200 bg-white/70 p-3"
              key={`${direction}-${index}`}
            >
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
                    {Array.from(
                      new Set([
                        port.data_type,
                        // All registered types (core + plugin + user-defined),
                        // matching AppBlock. Falls back to the core list if the
                        // hierarchy has not loaded yet.
                        ...(typeHierarchy.length > 0
                          ? typeHierarchy.map((t) => t.name)
                          : CODEBLOCK_DATA_TYPES),
                      ]),
                    ).map((typeName) => (
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
                <div className="min-w-0 self-end">
                  {/* ADR-043 boundary IO: input ports are written by a SAVER,
                      output ports read by a LOADER. Extensions are stored with a
                      leading dot here but the capability lookup wants none. */}
                  <CapabilityDropdown
                    direction={direction === "output" ? "load" : "save"}
                    dataType={port.data_type}
                    extension={port.extension.replace(/^\.+/, "")}
                    value={port.capability_id ?? null}
                    onChange={(capabilityId) =>
                      updatePort(index, { capability_id: capabilityId ?? "" })
                    }
                    id={`codeblock-${direction}-${port.name || index}`}
                    typeHierarchy={typeHierarchy}
                  />
                </div>
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
                {direction === "input" ? "Read from" : "Save into"}{" "}
                <code>{port.exchange_folder}</code>
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

export function CodeBlockConfigEditor({
  params,
  onUpdateConfig,
  typeHierarchy = [],
}: {
  params: Record<string, unknown>;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  typeHierarchy?: TypeHierarchyEntry[];
}) {
  const inputs = codeBlockPorts(params, "inputs", "input");
  const outputs = codeBlockPorts(params, "outputs", "output");

  const updatePorts = (
    key: "inputs" | "outputs",
    direction: CodeBlockPortDirection,
    ports: CodeBlockPortConfig[],
  ) => {
    // Hotfix 2026-05-23 — also mirror into ``input_ports`` / ``output_ports``
    // so the canvas variadic-port handles, the right-pane PortInfoPanel, and
    // the workflow edge color resolver see the same set of ports the user
    // edited in this table. Without this mirror the canvas kept stale ports
    // until the user clicked the canvas "+" button, which then wrote a
    // separate list. Layout alignment with Fiji's PortEditorTable is tracked
    // in #1324.
    const variadicKey = key === "inputs" ? "input_ports" : "output_ports";
    onUpdateConfig({
      [key]: ports.map((port) => persistCodeBlockPort(port, direction)),
      [variadicKey]: ports.map(variadicEntryFromCodeBlockPort),
    });
  };

  return (
    <div className="grid gap-5">
      {/* Declared inputs/outputs are CodeBlock's dynamic ports, so per the
          live UX pass they move to the top as the head section. They stay an
          explicit exception to the side-by-side port rule: each row carries
          six fields, so they remain full-width and stacked. */}
      <CodeBlockPortTable
        direction="input"
        onChange={(next) => updatePorts("inputs", "input", next)}
        ports={inputs}
        typeHierarchy={typeHierarchy}
      />
      <CodeBlockPortTable
        direction="output"
        onChange={(next) => updatePorts("outputs", "output", next)}
        ports={outputs}
        typeHierarchy={typeHierarchy}
      />

      <div className="grid gap-4 md:grid-cols-2">
        {/* script_path is a half-row cell and reuses the generic field so it
            carries the same file-browser button as every other block. */}
        <ConfigField
          fieldKey="script_path"
          field={{ type: "string", title: "Script path", ui_widget: "file_browser" }}
          currentValue={params.script_path ?? ""}
          onUpdateConfig={onUpdateConfig}
        />
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-ink">Interpreter mode</span>
          <select
            className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
            onChange={(event) => {
              const mode = event.target.value;
              // "auto" resolves SciStudio's own interpreter, so clear any
              // configured path — otherwise a hidden interpreter_path would
              // silently override auto. "existing" keeps the field visible.
              onUpdateConfig(
                mode === "auto"
                  ? { interpreter_mode: mode, interpreter_path: null }
                  : { interpreter_mode: mode },
              );
            }}
            value={String(params.interpreter_mode ?? "auto")}
          >
            <option value="auto">auto</option>
            <option value="existing">existing</option>
          </select>
        </label>
        {/* interpreter_path / exchange_root reuse the generic field for the
            same browse button: a file picker for the interpreter executable, a
            directory picker for the exchange root. interpreter_path is only
            meaningful (and required) in "existing" mode; in "auto" SciStudio
            resolves its own interpreter, so the field is hidden there.
            working_directory is removed: scripts always run from the project
            root (2026-06 config pass). */}
        {String(params.interpreter_mode ?? "auto") === "existing" && (
          <ConfigField
            fieldKey="interpreter_path"
            field={{ type: "string", title: "Interpreter path", ui_widget: "file_browser" }}
            currentValue={params.interpreter_path ?? ""}
            onUpdateConfig={onUpdateConfig}
          />
        )}
        <ConfigField
          fieldKey="exchange_root"
          field={{ type: "string", title: "Exchange root", ui_widget: "directory_browser" }}
          currentValue={params.exchange_root ?? "exchange"}
          onUpdateConfig={onUpdateConfig}
        />
        {/* Timeout removed (2026-06 config pass): CodeBlock always runs without
            a wall-clock timeout, so the editor no longer offers the field. */}
      </div>

      <CodeBlockEnvironmentEditor
        onUpdate={(next) => onUpdateConfig({ environment_variables: next })}
        value={params.environment_variables}
      />
    </div>
  );
}
