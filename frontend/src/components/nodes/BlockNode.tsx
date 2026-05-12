import { type Node, Handle, Position, type NodeProps, useEdges, useReactFlow } from "@xyflow/react";
import { useState, useEffect, useCallback, useRef, useLayoutEffect } from "react";

import { resolveTypeColor, resolveRingColor, isAnyType, primaryTypeName } from "../../config/typeColorMap";
import { api, ApiError } from "../../lib/api";
import type { FilesystemEntry } from "../../types/api";
import type { BlockNodeData } from "../../types/ui";
import { computeEffectivePorts } from "../../utils/computeEffectivePorts";

// ---------------------------------------------------------------------------
// Category icon map
// ---------------------------------------------------------------------------
const categoryIcons: Record<string, string> = {
  io: "\uD83D\uDCC1",
  process: "\u2699\uFE0F",
  code: "\uD83D\uDCBB",
  app: "\uD83D\uDDA5\uFE0F",
  ai: "\u2728",
  subworkflow: "\uD83D\uDCE6",
  custom: "\uD83E\uDDE9",
};

// ---------------------------------------------------------------------------
// State badge configuration
// ---------------------------------------------------------------------------
interface BadgeStyle {
  icon: string;
  label: string;
  bg: string;
  text: string;
  spin?: boolean;
  italic?: boolean;
  clickable?: boolean;
}

const badgeStyles: Record<string, BadgeStyle> = {
  idle: { icon: "\u25CB", label: "Idle", bg: "rgba(156,163,175,0.15)", text: "#9CA3AF" },
  ready: { icon: "\u25C9", label: "Ready", bg: "rgba(59,130,246,0.15)", text: "#3B82F6" },
  running: { icon: "\u27F3", label: "Running", bg: "rgba(59,130,246,0.15)", text: "#3B82F6", spin: true },
  paused: { icon: "\u23F8", label: "Paused", bg: "rgba(245,158,11,0.15)", text: "#F59E0B" },
  done: { icon: "\u2705", label: "Done", bg: "rgba(34,197,94,0.15)", text: "#22C55E" },
  error: { icon: "\u274C", label: "Error", bg: "rgba(239,68,68,0.15)", text: "#EF4444", clickable: true },
  cancelled: { icon: "\u2298", label: "Cancelled", bg: "rgba(249,115,22,0.15)", text: "#F97316" },
  skipped: { icon: "\u2298", label: "Skipped", bg: "rgba(156,163,175,0.15)", text: "#9CA3AF", italic: true },
};

// ---------------------------------------------------------------------------
// StatusBadge sub-component
// ---------------------------------------------------------------------------
function StatusBadge({
  status,
  onErrorClick,
}: {
  status?: string;
  onErrorClick?: () => void;
}) {
  const style = badgeStyles[status ?? "idle"] ?? badgeStyles.idle;

  const inner = (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none"
      style={{
        backgroundColor: style.bg,
        color: style.text,
        fontStyle: style.italic ? "italic" : undefined,
        cursor: style.clickable ? "pointer" : undefined,
      }}
    >
      <span className={style.spin ? "inline-block animate-spin" : undefined}>
        {style.icon}
      </span>
      {style.label}
    </span>
  );

  if (style.clickable && onErrorClick) {
    return (
      <button type="button" onClick={onErrorClick} className="focus:outline-none">
        {inner}
      </button>
    );
  }

  return inner;
}

// ---------------------------------------------------------------------------
// FileBrowserModal — lazy-loading filesystem picker for ui_widget fields
// ---------------------------------------------------------------------------
function FileBrowserModal({
  mode,
  initialPath,
  onSelect,
  onCancel,
}: {
  mode: "file_browser" | "directory_browser";
  initialPath: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
}) {
  const [currentPath, setCurrentPath] = useState("");
  const [entries, setEntries] = useState<FilesystemEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<string | null>(null);

  const loadDirectory = useCallback(async (dirPath: string) => {
    setLoading(true);
    setError(null);
    setSelectedEntry(null);
    try {
      const resp = await api.browseFilesystem(dirPath);
      setCurrentPath(resp.path);
      setEntries(resp.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to browse");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Try to start from the current value's directory
    const startPath = initialPath || "";
    loadDirectory(startPath);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const breadcrumbs = currentPath
    ? currentPath.replace(/\\/g, "/").split("/").filter(Boolean)
    : [];

  const handleNavigate = (dirName: string) => {
    const sep = currentPath.includes("\\") ? "\\" : "/";
    const newPath = currentPath ? `${currentPath}${sep}${dirName}` : dirName;
    loadDirectory(newPath);
  };

  const handleBreadcrumbClick = (index: number) => {
    if (index < 0) {
      // Go to roots
      loadDirectory("");
      return;
    }
    const parts = currentPath.replace(/\\/g, "/").split("/").filter(Boolean);
    // On Windows paths like "C:/" we need to preserve the drive letter
    const isWindows = currentPath.includes("\\") || (/^[A-Z]:/.test(currentPath));
    let newPath: string;
    if (isWindows) {
      newPath = parts.slice(0, index + 1).join("\\");
      if (/^[A-Z]:$/.test(newPath)) newPath += "\\";
    } else {
      newPath = "/" + parts.slice(0, index + 1).join("/");
    }
    loadDirectory(newPath);
  };

  const handleSelect = () => {
    if (mode === "directory_browser") {
      // Select the current directory or a selected sub-directory
      if (selectedEntry) {
        const sep = currentPath.includes("\\") ? "\\" : "/";
        onSelect(`${currentPath}${sep}${selectedEntry}`);
      } else {
        onSelect(currentPath);
      }
    } else {
      // file_browser: must have a selected file
      if (selectedEntry) {
        const sep = currentPath.includes("\\") ? "\\" : "/";
        onSelect(`${currentPath}${sep}${selectedEntry}`);
      }
    }
  };

  const formatSize = (size: number | null | undefined): string => {
    if (size == null) return "";
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  };

  const canSelect =
    mode === "directory_browser"
      ? currentPath !== "" || selectedEntry != null
      : selectedEntry != null &&
        entries.some((e) => e.name === selectedEntry && e.type === "file");

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      onClick={onCancel}
    >
      <div
        className="flex max-h-[70vh] w-[500px] flex-col rounded-xl border border-stone-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-stone-100 px-4 py-3">
          <div className="text-sm font-semibold text-ink">
            {mode === "file_browser" ? "Select File" : "Select Directory"}
          </div>
          {/* Breadcrumbs */}
          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-stone-500">
            <button
              type="button"
              className="hover:text-sea"
              onClick={() => handleBreadcrumbClick(-1)}
            >
              Root
            </button>
            {breadcrumbs.map((part, i) => (
              <span key={i} className="flex items-center gap-1">
                <span>/</span>
                <button
                  type="button"
                  className="hover:text-sea"
                  onClick={() => handleBreadcrumbClick(i)}
                >
                  {part}
                </button>
              </span>
            ))}
          </div>
        </div>

        {/* File list */}
        <div className="min-h-[200px] flex-1 overflow-y-auto px-2 py-1">
          {loading && (
            <p className="py-4 text-center text-xs text-stone-400">Loading...</p>
          )}
          {error && (
            <p className="py-4 text-center text-xs text-red-500">{error}</p>
          )}
          {!loading && !error && entries.length === 0 && (
            <p className="py-4 text-center text-xs text-stone-400">
              Empty directory
            </p>
          )}
          {!loading &&
            !error &&
            entries.map((entry) => {
              const isDir = entry.type === "directory";
              const isSelected = selectedEntry === entry.name;
              const isSelectable =
                mode === "directory_browser" ? isDir : true;
              return (
                <div
                  key={entry.name}
                  className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs ${
                    isSelected
                      ? "bg-blue-50 text-sea"
                      : "text-ink hover:bg-stone-50"
                  } ${!isSelectable && mode === "file_browser" && !isDir ? "opacity-50" : ""}`}
                  onClick={() => {
                    if (isDir) {
                      // Double-click navigates; single click selects for directory_browser
                      if (mode === "directory_browser") {
                        setSelectedEntry(isSelected ? null : entry.name);
                      }
                    } else {
                      if (mode === "file_browser") {
                        setSelectedEntry(isSelected ? null : entry.name);
                      }
                    }
                  }}
                  onDoubleClick={() => {
                    if (isDir) {
                      handleNavigate(entry.name);
                    } else if (mode === "file_browser") {
                      const sep = currentPath.includes("\\") ? "\\" : "/";
                      onSelect(`${currentPath}${sep}${entry.name}`);
                    }
                  }}
                >
                  <span className="shrink-0 text-sm">
                    {isDir ? "\uD83D\uDCC1" : "\uD83D\uDCC4"}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                  {!isDir && entry.size != null && (
                    <span className="shrink-0 text-stone-400">
                      {formatSize(entry.size)}
                    </span>
                  )}
                </div>
              );
            })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-stone-100 px-4 py-2">
          <button
            type="button"
            className="rounded border border-stone-200 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded bg-blue-500 px-3 py-1.5 text-xs text-white hover:bg-blue-600 disabled:opacity-40"
            disabled={!canSelect}
            onClick={handleSelect}
          >
            Select
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline config helpers
// ---------------------------------------------------------------------------
interface ConfigProperty {
  key: string;
  schema: Record<string, unknown>;
}

function getTopConfigProperties(
  configSchema?: { properties?: Record<string, Record<string, unknown>> },
): ConfigProperty[] {
  if (!configSchema?.properties) return [];

  return Object.entries(configSchema.properties)
    .map(([key, schema]) => ({ key, schema }))
    .sort((a, b) => {
      const pa = (a.schema.ui_priority as number) ?? 999;
      const pb = (b.schema.ui_priority as number) ?? 999;
      return pa - pb;
    })
    .slice(0, 3);
}

function InlineConfigField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: (key: string, val: unknown) => void;
}) {
  const { key, schema } = prop;
  const label = (schema.title as string) ?? key;

  // Enum dropdown
  if (Array.isArray(schema.enum)) {
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span className="shrink-0 text-stone-500">{label}</span>
        <select
          className="nodrag nowheel min-w-0 flex-1 truncate rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          value={String(value ?? schema.default ?? "")}
          onChange={(e) => onChange(key, e.target.value)}
        >
          {(schema.enum as unknown[]).map((opt) => (
            <option key={String(opt)} value={String(opt)}>
              {String(opt)}
            </option>
          ))}
        </select>
      </label>
    );
  }

  // Boolean checkbox
  if (schema.type === "boolean") {
    const checked = (value ?? schema.default ?? false) as boolean;
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span className="text-stone-500">{label}</span>
        <input
          type="checkbox"
          className="nodrag nowheel h-4 w-4 accent-sea"
          checked={checked}
          onChange={(e) => onChange(key, e.target.checked)}
        />
      </label>
    );
  }

  // Number input
  if (schema.type === "number" || schema.type === "integer") {
    return (
      <label className="flex items-center justify-between gap-2 text-xs">
        <span className="shrink-0 text-stone-500">{label}</span>
        <input
          type="number"
          className="nodrag nowheel min-w-0 flex-1 rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          value={value != null ? String(value) : String(schema.default ?? "")}
          onChange={(e) => {
            const num = Number(e.target.value);
            onChange(key, Number.isNaN(num) ? e.target.value : num);
          }}
        />
      </label>
    );
  }

  // Textarea widget — multi-line text editing (e.g. AI block prompt).
  // Any block can opt in by declaring "ui_widget": "textarea" in its
  // config_schema property.
  if ((schema.ui_widget as string | undefined) === "textarea") {
    return (
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-stone-500">{label}</span>
        <textarea
          className="nodrag nowheel w-full resize-y rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          rows={6}
          placeholder={`Enter ${label.toLowerCase()}...`}
          value={String(value ?? schema.default ?? "")}
          onChange={(e) => onChange(key, e.target.value)}
        />
      </label>
    );
  }

  // Default: text input. When ui_widget is "file_browser" or
  // "directory_browser", render a "..." browse button next to the input
  // that opens the FileBrowserModal (#484).
  const uiWidget = schema.ui_widget as string | undefined;
  const hasBrowse =
    uiWidget === "file_browser" || uiWidget === "directory_browser";
  const [browseOpen, setBrowseOpen] = useState(false);
  const [clipCopied, setClipCopied] = useState(false);

  const handleBrowseClick = async () => {
    // Try native OS dialog first, fall back to in-app FileBrowserModal
    const nativeMode = uiWidget === "directory_browser" ? "directory" : "file";
    const currentVal = String(value ?? schema.default ?? "");
    // Extract parent directory from current value for initial_dir
    let initialDir: string | undefined;
    if (currentVal) {
      const sep = currentVal.includes("\\") ? "\\" : "/";
      const parts = currentVal.split(sep);
      if (parts.length > 1 && uiWidget === "file_browser") {
        const last = parts[parts.length - 1];
        if (last.includes(".")) {
          initialDir = parts.slice(0, -1).join(sep);
        } else {
          initialDir = currentVal;
        }
      } else {
        initialDir = currentVal;
      }
    }
    try {
      const result = await api.openNativeDialog(nativeMode, initialDir);
      if (result.paths.length > 0) {
        // Only pass an array when the field schema explicitly supports it
        // (type includes "array"). Fields like app_command and script_path
        // are pure strings and must not receive an array.
        const schemaType = schema.type;
        const supportsArray =
          Array.isArray(schemaType)
            ? schemaType.includes("array")
            : schemaType === "array";
        if (supportsArray && result.paths.length > 1) {
          onChange(key, result.paths);
        } else {
          onChange(key, result.paths[0]);
        }
      }
      // If paths is empty, user cancelled — do nothing
    } catch (err) {
      // Status-aware fallback (#678):
      //  - HTTP 500 = native dialog tool not installed on this platform → fall
      //    back to the deprecated in-app FileBrowserModal so the user can still
      //    pick a path.
      //  - HTTP 504 = dialog timed out. Backend no longer enforces a timeout
      //    so this should not happen in practice; if it does, do NOT fall back
      //    silently — surface the error so we notice. Just log; the deprecated
      //    in-app picker is a worse experience than a no-op.
      //  - Any other error (network failure, unknown) → fall back defensively.
      if (err instanceof ApiError) {
        if (err.status === 504) {
          // eslint-disable-next-line no-console
          console.error(
            "Native file dialog timed out (HTTP 504); not falling back to in-app picker.",
            err,
          );
          return;
        }
        // 500 and any other HTTP error: fall back to in-app picker.
        setBrowseOpen(true);
        return;
      }
      // Non-ApiError (network failure, etc.): fall back defensively.
      setBrowseOpen(true);
    }
  };

  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-stone-500">{label}</span>
      <div className="flex min-w-0 flex-1 gap-1">
        <input
          type="text"
          className="nodrag nowheel min-w-0 flex-1 truncate rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          placeholder={key === "path" || key === "script_path" ? "Type or paste path" : undefined}
          title={String(value ?? schema.default ?? "")}
          value={String(value ?? schema.default ?? "")}
          onChange={(e) => onChange(key, e.target.value)}
        />
        {hasBrowse && (
          <button
            type="button"
            className="nodrag shrink-0 rounded border border-stone-200 bg-white px-1.5 py-1 text-xs text-stone-600 hover:bg-stone-50"
            title="Browse filesystem"
            onClick={() => void handleBrowseClick()}
          >
            ...
          </button>
        )}
        {uiWidget === "directory_browser" && (
          <button
            type="button"
            className="nodrag shrink-0 rounded border border-stone-200 bg-white px-1.5 py-1 text-xs text-stone-600 hover:bg-stone-50"
            title={clipCopied ? "Copied!" : "Copy path to clipboard"}
            onClick={() => {
              const val = String(value ?? schema.default ?? "");
              if (val) {
                void navigator.clipboard.writeText(val);
                setClipCopied(true);
                setTimeout(() => setClipCopied(false), 1500);
              }
            }}
          >
            {clipCopied ? (
              <span className="text-green-600 text-[10px]">{"\u2713"}</span>
            ) : (
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="5" y="5" width="9" height="9" rx="1" />
                <path d="M11 5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h2" />
              </svg>
            )}
          </button>
        )}
      </div>
      {browseOpen && hasBrowse && (
        <FileBrowserModal
          mode={uiWidget as "file_browser" | "directory_browser"}
          initialPath={(() => {
            // Try to extract the parent directory from the current value
            const val = String(value ?? schema.default ?? "");
            if (!val) return "";
            // If it looks like a file path, use its parent directory
            const sep = val.includes("\\") ? "\\" : "/";
            const parts = val.split(sep);
            if (parts.length > 1) {
              // Could be a file — check if last part has an extension
              const last = parts[parts.length - 1];
              if (uiWidget === "file_browser" && last.includes(".")) {
                return parts.slice(0, -1).join(sep);
              }
            }
            return val;
          })()}
          onSelect={(selectedPath) => {
            onChange(key, selectedPath);
            setBrowseOpen(false);
          }}
          onCancel={() => setBrowseOpen(false)}
        />
      )}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Error message inline display
// ---------------------------------------------------------------------------
const MAX_INLINE_ERROR_LEN = 80;
const MAX_TOOLTIP_LINES = 10;

function ErrorMessage({ message }: { message: string }) {
  const truncated =
    message.length > MAX_INLINE_ERROR_LEN
      ? `${message.slice(0, MAX_INLINE_ERROR_LEN)}…`
      : message;

  // Build a tooltip that shows up to MAX_TOOLTIP_LINES lines of the error
  const lines = message.split("\n");
  const tooltipText =
    lines.length > MAX_TOOLTIP_LINES
      ? lines.slice(0, MAX_TOOLTIP_LINES).join("\n") + "\n…(click for full trace)"
      : message;

  return (
    <span
      className="ml-2 min-w-0 flex-1 truncate text-[10px] leading-tight text-red-500"
      title={tooltipText}
    >
      {truncated}
    </span>
  );
}

// ---------------------------------------------------------------------------
// BlockNode component
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// PausedToast — shown when an AppBlock enters PAUSED state
// ---------------------------------------------------------------------------
function PausedToast({ outputDir }: { outputDir: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = () => {
    if (outputDir) void navigator.clipboard.writeText(outputDir);
    setCopied(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="mt-1 flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700">
      <span className="min-w-0 flex-1 truncate" title={outputDir}>
        Save outputs to: {outputDir || "(exchange dir)"}
      </span>
      {outputDir && (
        <button
          type="button"
          className="nodrag shrink-0 rounded border border-amber-300 bg-white px-1 py-0.5 text-[10px] text-amber-700 hover:bg-amber-50"
          title="Copy output path"
          onClick={handleCopy}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  );
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
  const typeHierarchy = data.schema?.type_hierarchy;
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
  const drivingConfigValue =
    sourceConfigKey != null
      ? (data.config?.[sourceConfigKey] as string | undefined)
      : undefined;
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

  // Measure the header + config section height to position port handles
  // below the variable-height content instead of using a hardcoded offset.
  const configSectionRef = useRef<HTMLDivElement>(null);
  const [portStartY, setPortStartY] = useState(80);
  useLayoutEffect(() => {
    if (configSectionRef.current) {
      // Use offsetTop + offsetHeight instead of getBoundingClientRect()
      // because offset* properties are in the node's local coordinate
      // system, unaffected by ReactFlow's CSS zoom transform.
      const offset = configSectionRef.current.offsetTop + configSectionRef.current.offsetHeight + 8;
      setPortStartY(offset);
    }
    // Re-measure only when config properties or port lists change, not on
    // every render (which causes port jitter during edge dragging).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configProps.length, effectiveInputPorts.length, effectiveOutputPorts.length]);

  const handleConfigChange = (key: string, value: unknown) => {
    data.onUpdateConfig?.({ [key]: value });
  };

  // ADR-029 D2: variadic port UI — [+] and [-] controls.
  const edges = useEdges();
  const isVariadicInputs = data.schema?.variadic_inputs === true;
  const isVariadicOutputs = data.schema?.variadic_outputs === true;

  // ADR-029 Addendum 1: min/max port count limits.
  const minInputPorts = data.schema?.min_input_ports ?? null;
  const maxInputPorts = data.schema?.max_input_ports ?? null;
  const minOutputPorts = data.schema?.min_output_ports ?? null;
  const maxOutputPorts = data.schema?.max_output_ports ?? null;
  const canAddInput = maxInputPorts == null || effectiveInputPorts.length < maxInputPorts;
  const canRemoveInput = minInputPorts == null || effectiveInputPorts.length > minInputPorts;
  const canAddOutput = maxOutputPorts == null || effectiveOutputPorts.length < maxOutputPorts;
  const canRemoveOutput = minOutputPorts == null || effectiveOutputPorts.length > minOutputPorts;

  const { deleteElements } = useReactFlow();

  const handleAddPort = (direction: "input" | "output") => {
    const key = direction === "input" ? "input_ports" : "output_ports";
    const current = Array.isArray(data.config?.[key]) ? (data.config[key] as Array<{name: string; types: string[]}>) : [];
    const defaultType = direction === "input"
      ? (data.schema?.allowed_input_types?.[0] ?? "DataObject")
      : (data.schema?.allowed_output_types?.[0] ?? "DataObject");
    data.onUpdateConfig?.({
      [key]: [...current, { name: `port_${current.length + 1}`, types: [defaultType] }],
    });
  };

  const handleRemovePort = (direction: "input" | "output", portName: string) => {
    const connected = edges.filter(
      (e) =>
        (direction === "input" && e.target === nodeId && e.targetHandle === portName) ||
        (direction === "output" && e.source === nodeId && e.sourceHandle === portName),
    );
    if (connected.length > 0) {
      const confirmed = window.confirm(
        `This port has ${connected.length} connection(s). Remove port and disconnect?`,
      );
      if (!confirmed) return;
      deleteElements({ edges: connected });
    }
    const key = direction === "input" ? "input_ports" : "output_ports";
    const current = Array.isArray(data.config?.[key]) ? (data.config[key] as Array<{name: string; types: string[]}>) : [];
    data.onUpdateConfig?.({ [key]: current.filter((p) => p.name !== portName) });
  };

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
          <span className="truncate font-display text-sm font-semibold text-ink">
            {data.label}
          </span>
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
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M13 8a5 5 0 1 1-1.5-3.5M13 3v2.5h-2.5" />
            </svg>
          </button>
          <button
            type="button"
            className="nodrag rounded p-1 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-500"
            title="Remove block"
            onClick={() => data.onDelete?.()}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Inline config                                                     */}
      {/* ----------------------------------------------------------------- */}
      <div ref={configSectionRef} className="nodrag nowheel space-y-2 overflow-hidden border-b border-stone-100 px-3 py-2">
        {configProps.length > 0 ? (
          configProps.map((prop) => (
            <InlineConfigField
              key={prop.key}
              prop={prop}
              value={data.config?.[prop.key]}
              onChange={handleConfigChange}
            />
          ))
        ) : (
          <p className="text-center text-[11px] italic text-stone-400">
            No parameters
          </p>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Port handles (positioned absolutely by React Flow)                */}
      {/* ----------------------------------------------------------------- */}
      {/* Use effective ports so dynamic blocks (LoadData, SaveData) get   */}
      {/* per-instance accepted_types resolved from data.schema?.dynamic_ports */}
      {/* + the current driving config value (ADR-028 Addendum 1 §D4).      */}
      {effectiveInputPorts.map((port, index) => {
        const fillColor = resolveTypeColor(port.accepted_types, typeHierarchy);
        const ringColor = resolveRingColor(port.accepted_types, typeHierarchy);
        const anyType = isAnyType(port.accepted_types);
        const typeName = primaryTypeName(port.accepted_types);
        const borderColor = ringColor ?? (anyType ? "#d1d5db" : fillColor);
        const portTop = portStartY + index * 20;
        return (
          <span key={port.name} className="group">
            <Handle
              id={port.name}
              type="target"
              position={Position.Left}
              className="!h-3.5 !w-3.5 !border-2"
              title={`${typeName}${port.description ? " \u2014 " + port.description : ""}`}
              style={{
                backgroundColor: anyType ? "#ffffff" : fillColor,
                borderColor,
                borderStyle: anyType ? "dashed" : "solid",
                left: -7,
                top: portTop,
              }}
            />
            {isVariadicInputs && canRemoveInput && (
              <button
                type="button"
                className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-100 text-[9px] text-red-500 opacity-0 transition-opacity hover:bg-red-200 group-hover:opacity-100"
                title={`Remove port "${port.name}"`}
                style={{ left: 6, top: portTop - 1 }}
                onClick={() => handleRemovePort("input", port.name)}
              >
                ×
              </button>
            )}
          </span>
        );
      })}
      {isVariadicInputs && canAddInput && (
        <button
          type="button"
          className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-stone-100 text-[9px] text-stone-500 transition-colors hover:bg-ember hover:text-white"
          title="Add input port"
          style={{ left: -7, top: portStartY + effectiveInputPorts.length * 20 - 1 }}
          onClick={() => handleAddPort("input")}
        >
          +
        </button>
      )}
      {effectiveOutputPorts.map((port, index) => {
        const fillColor = resolveTypeColor(port.accepted_types, typeHierarchy);
        const ringColor = resolveRingColor(port.accepted_types, typeHierarchy);
        const anyType = isAnyType(port.accepted_types);
        const typeName = primaryTypeName(port.accepted_types);
        const borderColor = ringColor ?? (anyType ? "#d1d5db" : fillColor);
        const portTop = portStartY + index * 20;
        return (
          <span key={port.name} className="group">
            <Handle
              id={port.name}
              type="source"
              position={Position.Right}
              className="!h-3.5 !w-3.5 !border-2"
              title={`${typeName}${port.description ? " \u2014 " + port.description : ""}`}
              style={{
                backgroundColor: anyType ? "#ffffff" : fillColor,
                borderColor,
                borderStyle: anyType ? "dashed" : "solid",
                right: -7,
                top: portTop,
              }}
            />
            {isVariadicOutputs && canRemoveOutput && (
              <button
                type="button"
                className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-100 text-[9px] text-red-500 opacity-0 transition-opacity hover:bg-red-200 group-hover:opacity-100"
                title={`Remove port "${port.name}"`}
                style={{ right: 6, top: portTop - 1 }}
                onClick={() => handleRemovePort("output", port.name)}
              >
                ×
              </button>
            )}
          </span>
        );
      })}
      {isVariadicOutputs && canAddOutput && (
        <button
          type="button"
          className="nodrag absolute flex h-3.5 w-3.5 items-center justify-center rounded-full bg-stone-100 text-[9px] text-stone-500 transition-colors hover:bg-ember hover:text-white"
          title="Add output port"
          style={{ right: -7, top: portStartY + effectiveOutputPorts.length * 20 - 1 }}
          onClick={() => handleAddPort("output")}
        >
          +
        </button>
      )}

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
