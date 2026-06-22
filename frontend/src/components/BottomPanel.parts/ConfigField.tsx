import { useState } from "react";

import { api, ApiError } from "../../lib/api";
import { FileBrowserModal } from "../nodes/BlockNode.parts/FileBrowserModal";

import { CaretPreservingTextArea, CaretPreservingTextInput } from "./CaretPreservingTextInput";

type BrowseMode = "file" | "directory" | null;

function browseModeFor(uiWidget: string | undefined): BrowseMode {
  if (uiWidget === "file_browser") return "file";
  if (uiWidget === "directory_browser") return "directory";
  return null;
}

/**
 * Pick a single representative path from a field value for seeding the browse
 * dialog. A multi-file field holds an array; browsing must start from the first
 * selected path, NOT `String(array)` (a comma-joined concatenation of every
 * path), which builds an over-length, non-existent path and 500s the backend
 * filesystem endpoints (#1753).
 */
function firstPathOf(value: unknown): string {
  if (Array.isArray(value)) {
    const first = value.find((v) => typeof v === "string" && v.length > 0);
    return typeof first === "string" ? first : "";
  }
  return value == null ? "" : String(value);
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
  // Optional display labels keyed by enum value (e.g. permission_mode shows
  // "Ask"/"Bypass" while persisting "safe"/"bypass"). Falls back to the value.
  const enumLabels = (field.ui_enum_labels ?? {}) as Record<string, string>;
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
            {enumLabels[String(option)] ?? String(option)}
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
    const checked = Boolean(currentValue);
    return (
      // Match the text-field footprint (title above a bordered control row) so a
      // boolean renders symmetrically beside text inputs in the 2-column config
      // grid instead of a bare checkbox that only fills half the cell.
      <label className="grid gap-2 text-sm" key={fieldKey}>
        <span className="font-medium text-ink">{String(field.title ?? fieldKey)}</span>
        <div className="flex items-center gap-3 rounded-2xl border border-stone-300 bg-white px-4 py-3">
          <input
            checked={checked}
            className="h-4 w-4 rounded border-stone-300"
            onChange={(event) => onUpdateConfig({ [fieldKey]: event.target.checked })}
            type="checkbox"
          />
          <span className="text-stone-600">{checked ? "Enabled" : "Disabled"}</span>
        </div>
      </label>
    );
  }

  const uiWidget = field.ui_widget as string | undefined;
  if (uiWidget === "textarea") {
    // Multiline field. ``grid-rows-[auto_1fr]`` + ``h-full`` let the textarea
    // fill the (possibly row-spanned) grid cell so a tall prompt occupies the
    // whole space allotted by ConfigPanel.
    return (
      <label className="grid h-full grid-rows-[auto_1fr] gap-2 text-sm" key={fieldKey}>
        <span className="font-medium text-ink">{String(field.title ?? fieldKey)}</span>
        <CaretPreservingTextArea
          className="h-full min-h-[7rem] w-full min-w-0 resize-y rounded-2xl border border-stone-300 bg-white px-4 py-3"
          onChange={(next) => onUpdateConfig({ [fieldKey]: next })}
          value={String(currentValue ?? "")}
        />
      </label>
    );
  }
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
        nativeInitialDir(browseMode, firstPathOf(currentValue)),
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
          initialPath={modalInitialPath(browseMode, firstPathOf(currentValue))}
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

export function ConfigField({
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
