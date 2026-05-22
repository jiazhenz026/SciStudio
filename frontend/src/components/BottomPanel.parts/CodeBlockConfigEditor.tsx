import { Plus, Trash2 } from "lucide-react";

import { CaretPreservingTextInput } from "./CaretPreservingTextInput";
import {
  CODEBLOCK_DATA_TYPES,
  type CodeBlockPortConfig,
  type CodeBlockPortDirection,
  codeBlockFolder,
  codeBlockPorts,
  isRecord,
  nextCodeBlockPortName,
  persistCodeBlockPort,
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
                    {Array.from(new Set([port.data_type, ...CODEBLOCK_DATA_TYPES])).map(
                      (typeName) => (
                        <option key={typeName} value={typeName}>
                          {typeName}
                        </option>
                      ),
                    )}
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
}: {
  params: Record<string, unknown>;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const inputs = codeBlockPorts(params, "inputs", "input");
  const outputs = codeBlockPorts(params, "outputs", "output");

  const updatePorts = (
    key: "inputs" | "outputs",
    direction: CodeBlockPortDirection,
    ports: CodeBlockPortConfig[],
  ) => {
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
            onChange={(next) =>
              onUpdateConfig({ timeout_seconds: next === "" ? null : Number(next) })
            }
            type="number"
            value={
              params.timeout_seconds === null || params.timeout_seconds === undefined
                ? ""
                : String(params.timeout_seconds)
            }
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
