import type { TypeHierarchyEntry } from "../types/api";

import { CapabilityDropdown } from "./PortEditor/CapabilityDropdown";

export interface PortRow {
  name: string;
  types: string[];
  /** Issue #680: file extension (no leading dot, case-insensitive) used by the
   *  AppBlock runtime to bin saved files into output ports. Only meaningful
   *  for output ports. */
  extension?: string;
  /** ADR-043 FR-012: capability_id selected via the CapabilityDropdown.
   *  Only meaningful when `showCapabilityDropdown` is true. Null/undefined
   *  means "use the registry's default capability for this (type, extension)". */
  capability_id?: string | null;
}

interface PortEditorTableProps {
  direction: "input" | "output";
  ports: PortRow[];
  /** Type names allowed for this direction. Empty = show all from typeHierarchy. */
  allowedTypes: string[];
  typeHierarchy: TypeHierarchyEntry[];
  onChange: (ports: PortRow[]) => void;
  /** ADR-029 Addendum 1: minimum number of ports. null/undefined = no minimum. */
  minPorts?: number | null;
  /** ADR-029 Addendum 1: maximum number of ports. null/undefined = no maximum. */
  maxPorts?: number | null;
  /** Issue #680: when true, render the extension column for output ports.
   *  Defaults to true for output direction. Input ports never show this
   *  column because they have no file context. */
  showExtensionColumn?: boolean;
  /** ADR-043 FR-012: when true, render a CapabilityDropdown below each
   *  port row so the user can pin a stable capability_id. Defaults to
   *  true when `showExtensionColumn` is also true (output ports with a
   *  file context); inputs / variadic-without-extension ports skip the
   *  dropdown because the (direction, type, extension) tuple is not
   *  fully specified. */
  showCapabilityDropdown?: boolean;
}

/**
 * #1789: a port's `allowedTypes` lists the *base* types the block accepts. A
 * type is selectable if it IS one of those names or DESCENDS from one — i.e. its
 * `base_type` ancestry chain reaches an allowed name. Filtering by exact name
 * membership (the previous behaviour) meant a block that allows the root type
 * `DataObject` only offered the literal "DataObject" and excluded every subtype
 * (Image, DataFrame, Spectrum, …), even though they are all valid DataObjects.
 * An empty `allowedTypes` means "no constraint": show the whole hierarchy.
 */
export function filterAllowedTypes(
  typeHierarchy: TypeHierarchyEntry[],
  allowedTypes: string[],
): TypeHierarchyEntry[] {
  if (allowedTypes.length === 0) {
    return typeHierarchy;
  }
  const allowed = new Set(allowedTypes);
  const byName = new Map(typeHierarchy.map((t) => [t.name, t]));
  const isAllowed = (entry: TypeHierarchyEntry): boolean => {
    let current: TypeHierarchyEntry | undefined = entry;
    const seen = new Set<string>();
    // Walk the base_type chain (Image -> Array -> DataObject -> ""), stopping at
    // the root or a cycle. `seen` guards against a malformed self/loop chain.
    while (current && !seen.has(current.name)) {
      if (allowed.has(current.name)) {
        return true;
      }
      seen.add(current.name);
      current = current.base_type ? byName.get(current.base_type) : undefined;
    }
    return false;
  };
  return typeHierarchy.filter(isAllowed);
}

/**
 * Normalise an extension string the same way the backend does:
 * lowercase, strip any leading dots. Returns "" for empty input.
 */
function normalizeExtension(raw: string): string {
  let text = raw.trim();
  while (text.startsWith(".")) {
    text = text.slice(1);
  }
  return text.toLowerCase();
}

export function PortEditorTable({
  direction,
  ports,
  allowedTypes,
  typeHierarchy,
  onChange,
  minPorts,
  maxPorts,
  showExtensionColumn,
  showCapabilityDropdown,
}: PortEditorTableProps) {
  const availableTypes = filterAllowedTypes(typeHierarchy, allowedTypes);

  const defaultType = availableTypes[0]?.name ?? "DataObject";

  // ADR-029 Addendum 1: disable add/remove at min/max limits.
  const canAdd = maxPorts == null || ports.length < maxPorts;
  const canRemove = minPorts == null || ports.length > minPorts;

  // Issue #680: input ports never show the extension column; output ports
  // show it by default unless the caller explicitly opts out.
  const renderExtension = direction === "output" && (showExtensionColumn ?? true);

  // ADR-043 FR-012: only render the per-row CapabilityDropdown when the row
  // also exposes an extension input — without an extension the (direction,
  // type, extension) tuple cannot be resolved into a capability anyway.
  // Defaults to `renderExtension` so existing callers opt in automatically
  // and inputs / no-extension contexts opt out automatically.
  const renderCapability = renderExtension && (showCapabilityDropdown ?? true);

  function handleNameChange(index: number, name: string) {
    onChange(ports.map((p, i) => (i === index ? { ...p, name } : p)));
  }

  function handleTypeChange(index: number, typeName: string) {
    // Issue #1366: clearing `capability_id` on a type change prevents a stale
    // capability (pinned for the previous (direction, type, extension) tuple)
    // from surviving into a tuple where it is no longer registered. The user
    // re-selects via the CapabilityDropdown for the new tuple.
    onChange(
      ports.map((p, i) => (i === index ? { ...p, types: [typeName], capability_id: null } : p)),
    );
  }

  function handleExtensionChange(index: number, extension: string) {
    // Preserve the user's raw text so a leading dot (".csv") is kept, matching
    // the CodeBlock port editor. The backend normalises extensions when binning
    // and CapabilityDropdown is handed a normalised value, so the stored dot/
    // case is purely cosmetic.
    // Issue #1366 / PR #1397: still clear a pinned capability only when the
    // *normalised* extension actually changes (typing `csv` then `.CSV` is a
    // no-op for the (direction, type, extension) tuple, so the pin survives).
    const normalized = normalizeExtension(extension);
    onChange(
      ports.map((p, i) => {
        if (i !== index) return p;
        const capabilityChanged = normalizeExtension(p.extension ?? "") !== normalized;
        return {
          ...p,
          extension,
          capability_id: capabilityChanged ? null : p.capability_id,
        };
      }),
    );
  }

  function handleCapabilityChange(index: number, capabilityId: string) {
    onChange(ports.map((p, i) => (i === index ? { ...p, capability_id: capabilityId } : p)));
  }

  function handleRemove(index: number) {
    onChange(ports.filter((_, i) => i !== index));
  }

  function handleAdd() {
    const next: PortRow = { name: `port_${ports.length + 1}`, types: [defaultType] };
    if (renderExtension) {
      next.extension = "";
    }
    onChange([...ports, next]);
  }

  return (
    <div className="mb-4">
      <h3 className="mb-2 text-sm font-semibold text-ink">
        {direction === "input" ? "Input Ports" : "Output Ports"}
      </h3>
      <div className="flex flex-col gap-1.5">
        {ports.map((port, index) => (
          // Use the row index as the React key. Embedding `port.name` here
          // would remount the row on every keystroke in the name input
          // (since the controlled value changes), which drops focus after
          // a single character.
          <div className="flex flex-col gap-1" key={index}>
            <div className="flex items-center gap-2">
              <input
                className="w-32 rounded-xl border border-stone-300 bg-white px-3 py-1.5 text-sm"
                onChange={(e) => handleNameChange(index, e.target.value)}
                placeholder="port name"
                value={port.name}
              />
              <select
                className="min-w-0 flex-1 rounded-xl border border-stone-300 bg-white px-3 py-1.5 text-sm"
                onChange={(e) => handleTypeChange(index, e.target.value)}
                value={port.types[0] ?? defaultType}
              >
                {availableTypes.length > 0 ? (
                  availableTypes.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))
                ) : (
                  <option value="DataObject">DataObject</option>
                )}
              </select>
              {renderExtension && (
                <input
                  aria-label={`extension for ${port.name}`}
                  className="w-24 rounded-xl border border-stone-300 bg-white px-3 py-1.5 text-sm"
                  onChange={(e) => handleExtensionChange(index, e.target.value)}
                  placeholder="ext (e.g. .csv)"
                  value={port.extension ?? ""}
                />
              )}
              <button
                className={`rounded-lg px-2 py-1 text-xs ${canRemove ? "text-stone-500 hover:bg-red-100 hover:text-red-700" : "cursor-not-allowed text-stone-300"}`}
                disabled={!canRemove}
                onClick={() => handleRemove(index)}
                title={canRemove ? "Remove port" : `Minimum ${minPorts} port(s) required`}
                type="button"
              >
                −
              </button>
            </div>
            {renderCapability && (
              <div className="pl-2">
                <CapabilityDropdown
                  // ADR-043 boundary IO: at a block's IO boundary the runtime
                  // direction is inverted. An INPUT port is fed by a SAVER
                  // (SciStudio writes the DataObject to a file for the external
                  // app); an OUTPUT port is filled by a LOADER (the external app
                  // writes a file, SciStudio reads it back). The validator checks
                  // output ports with find_loader_capability(direction='load'),
                  // so the dropdown must list loaders for output ports.
                  direction={direction === "output" ? "load" : "save"}
                  dataType={port.types[0] ?? defaultType}
                  // Stored extension may now carry a leading dot / mixed case;
                  // normalise it for the capability lookup.
                  extension={normalizeExtension(port.extension ?? "")}
                  value={port.capability_id ?? null}
                  onChange={(capabilityId) => handleCapabilityChange(index, capabilityId)}
                  id={`${direction}-${port.name || index}`}
                  typeHierarchy={typeHierarchy}
                />
              </div>
            )}
          </div>
        ))}
        {ports.length === 0 && (
          <p className="text-xs text-stone-400">
            No ports defined. Click &quot;+ Add Port&quot; to add one.
          </p>
        )}
      </div>
      <button
        className={`mt-2 rounded-xl border px-3 py-1.5 text-sm ${canAdd ? "border-stone-300 bg-white text-stone-600 hover:bg-stone-50" : "cursor-not-allowed border-stone-200 bg-stone-50 text-stone-400"}`}
        disabled={!canAdd}
        onClick={handleAdd}
        title={canAdd ? undefined : `Maximum ${maxPorts} port(s) allowed`}
        type="button"
      >
        + Add Port
      </button>
    </div>
  );
}
