// Type colour resolution — one precedence, one source, two surfaces.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §7.1 FR-051 (precedence: type-declared colour → `typeColorMap` →
//   `hashTypeName`), FR-052 (an invalid declaration is ignored with a warning
//   and falls through), FR-066 (the types listing is the single source of type
//   colour; `type_hierarchy` keeps serving hierarchy and stops being a colour
//   transport), FR-067 (the resolvers must answer deterministically while the
//   types listing is still in flight).
//
// FR-067 is why `declared` is the *last* parameter and optional everywhere: a
// caller that has not received the types listing yet passes nothing and gets
// exactly the pre-ADR-053 answer, so the loading window renders the fallback
// rather than a placeholder. Every type that declares nothing — which is every
// type in the product today — therefore resolves byte-identically before and
// after the listing lands, and nothing flashes.

import type { TypeHierarchyEntry } from "../types/api";

// ---------------------------------------------------------------------------
// Base type color palette (#445)
// ---------------------------------------------------------------------------
export const typeColorMap: Record<string, string> = {
  Array: "#3b82f6",
  Image: "#3b82f6",
  Series: "#14b8a6",
  Spectrum: "#14b8a6",
  DataFrame: "#f59e0b",
  PeakTable: "#f59e0b",
  Text: "#22c55e",
  Artifact: "#6b7280",
  CompositeData: "#8b5cf6",
  Label: "#8b5cf6",
  Mask: "#3b82f6",
  // #1487: was #e5e7eb (gray-200), unreadable on white canvas. gray-700
  // keeps DataObject visually distinct from the saturated typed-port palette
  // while staying legible as the fallback color for unresolved port types.
  DataObject: "#374151",
};

// ---------------------------------------------------------------------------
// Subtype ring color map — subtypes that get a contrasting ring (#445)
// Key = type name, value = ring (border) color.
// ---------------------------------------------------------------------------
export const subtypeRingColorMap: Record<string, string> = {
  Image: "#ef4444",
  Label: "#ef4444",
  Mask: "#ec4899",
  Spectrum: "#ef4444",
  PeakTable: "#ef4444",
};

// ---------------------------------------------------------------------------
// Deterministic hash palette for unknown/plugin types (#543)
// ~20 visually distinct hues, avoiding colors too close to core type palette.
// ---------------------------------------------------------------------------
const HASH_PALETTE: string[] = [
  "#e11d48", // rose-600
  "#0891b2", // cyan-600
  "#7c3aed", // violet-600
  "#ea580c", // orange-600
  "#059669", // emerald-600
  "#d946ef", // fuchsia-500
  "#ca8a04", // yellow-600
  "#4f46e5", // indigo-600
  "#dc2626", // red-600
  "#0d9488", // teal-600
  "#9333ea", // purple-600
  "#c2410c", // orange-700
  "#0284c7", // sky-600
  "#65a30d", // lime-600
  "#db2777", // pink-600
  "#2563eb", // blue-600
  "#b45309", // amber-700
  "#7c2d12", // orange-900
  "#4338ca", // indigo-700
  "#15803d", // green-700
];

/**
 * Deterministic djb2 hash of a type name string.
 * Returns a non-negative 32-bit integer.
 */
export function hashTypeName(name: string): number {
  let hash = 5381;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) + hash + name.charCodeAt(i)) >>> 0;
  }
  return hash;
}

// ---------------------------------------------------------------------------
// Type-declared colour (ADR-053 FR-049 – FR-052, FR-066)
// ---------------------------------------------------------------------------

/** The colours one type declared, already validated. */
export interface DeclaredTypeColor {
  /** Validated fill, or absent when the type declared none/an unusable one. */
  fill?: string;
  /** Validated ring, or absent. */
  ring?: string;
}

/**
 * `type name → declared colours`, built from the types listing (FR-050).
 *
 * `undefined` at a call site means "the listing has not arrived" (FR-067), not
 * "nothing is declared"; an arrived-but-empty map means the latter. Both
 * resolve the same way, which is exactly what makes the loading window
 * invisible.
 */
export type DeclaredTypeColors = ReadonlyMap<string, DeclaredTypeColor>;

/** The shape `buildDeclaredTypeColors` needs — a subset of `TypeSummary`. */
export interface DeclaredTypeColorInput {
  name: string;
  ui_color?: string | null;
  ui_ring_color?: string | null;
}

/** `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` — the CSS hex forms the backend emits. */
const HEX_COLOUR_RE = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * Values already reported as unusable, so FR-052's warning is emitted once per
 * offending declaration rather than once per render. Canvas ports re-resolve
 * their colour on every render; without this a single typo in a user's type
 * file would flood the console.
 */
const warnedDeclarations = new Set<string>();

/**
 * Validate and normalise one declared colour, or return `undefined`.
 *
 * FR-052. The backend validates and normalises at collection time and sends
 * `null` for anything unusable, so this should never fire in practice — which
 * is precisely why it is here: a malformed hex string reaching the palette or
 * the canvas must degrade to the next precedence level, not break either
 * surface, whatever produced it.
 */
export function normalizeDeclaredColor(
  value: string | null | undefined,
  context: string,
): string | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  const trimmed = typeof value === "string" ? value.trim() : "";
  if (!HEX_COLOUR_RE.test(trimmed)) {
    const key = `${context}=${String(value)}`;
    if (!warnedDeclarations.has(key)) {
      warnedDeclarations.add(key);
      console.warn(
        `[typeColorMap] ignoring declared colour ${context}=${JSON.stringify(value)} — expected a CSS hex colour such as "#4f8ef7"; falling back to the default resolution`,
      );
    }
    return undefined;
  }
  const digits = trimmed.slice(1).toLowerCase();
  return digits.length <= 4
    ? `#${[...digits].map((digit) => digit + digit).join("")}`
    : `#${digits}`;
}

/**
 * Build the declared-colour lookup from a types listing response (FR-050).
 *
 * Derived once where the listing is stored rather than per render, so both
 * surfaces read one referentially stable map and neither re-derives colour on
 * every paint.
 */
export function buildDeclaredTypeColors(
  types: readonly DeclaredTypeColorInput[],
): DeclaredTypeColors {
  const declared = new Map<string, DeclaredTypeColor>();
  for (const type of types) {
    const fill = normalizeDeclaredColor(type.ui_color, `${type.name}.ui_color`);
    const ring = normalizeDeclaredColor(type.ui_ring_color, `${type.name}.ui_ring_color`);
    if (fill === undefined && ring === undefined) {
      continue;
    }
    const entry: DeclaredTypeColor = {};
    if (fill !== undefined) entry.fill = fill;
    if (ring !== undefined) entry.ring = ring;
    declared.set(type.name, entry);
  }
  return declared;
}

/** Test seam — forget which bad declarations have already been warned about. */
export function resetDeclaredColorWarnings(): void {
  warnedDeclarations.clear();
}

/**
 * Darken a hex color by a given amount (0-1) for ring color derivation.
 *
 * Accepts `#rrggbb` and `#rrggbbaa`; the alpha channel is dropped, which is
 * what a ring wants anyway.
 */
function darkenHex(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const factor = 1 - amount;
  const dr = Math.round(r * factor);
  const dg = Math.round(g * factor);
  const db = Math.round(b * factor);
  return `#${dr.toString(16).padStart(2, "0")}${dg.toString(16).padStart(2, "0")}${db.toString(16).padStart(2, "0")}`;
}

/**
 * Resolve the fill color for a port or a palette tile.
 *
 * FR-051 precedence, applied per accepted type in order:
 *   1. the colour the type itself declared, from the types listing (`declared`),
 *   2. the existing `typeColorMap` entry — directly, or through the type's
 *      `base_type` in the schema hierarchy,
 *   3. the deterministic `hashTypeName` fallback (#543).
 *
 * `declared` omitted (the FR-067 loading window) or empty leaves steps 2 and 3
 * exactly as they were before ADR-053, so an undeclared type is unchanged.
 *
 * `typeHierarchy` is consulted for `base_type` only. FR-066: it keeps serving
 * type hierarchy and is no longer a colour transport, because two supply points
 * for one fact are the drift this work exists to remove.
 */
export function resolveTypeColor(
  typeNames: string[],
  typeHierarchy?: TypeHierarchyEntry[],
  declared?: DeclaredTypeColors,
): string {
  for (const name of typeNames) {
    const own = declared?.get(name)?.fill;
    if (own) {
      return own;
    }
    if (typeColorMap[name]) {
      return typeColorMap[name];
    }
    if (typeHierarchy) {
      const entry = typeHierarchy.find((t) => t.name === name);
      if (entry?.base_type && typeColorMap[entry.base_type]) {
        return typeColorMap[entry.base_type];
      }
    }
  }
  // Hash-based fallback for unknown/plugin types (#543)
  if (typeNames.length > 0) {
    const idx = hashTypeName(typeNames[0]) % HASH_PALETTE.length;
    return HASH_PALETTE[idx];
  }
  return typeColorMap.DataObject;
}

/**
 * Resolve the ring (border) color for a port or a palette tile. Returns
 * `undefined` for base types that should not have a contrasting ring — those
 * render solid, their border taking the fill colour.
 *
 * FR-051 precedence, per accepted type:
 *   1. the ring the type itself declared,
 *   2. the existing `subtypeRingColorMap` entry,
 *   3. a ring derived from the type's *declared* fill, so a type that declared
 *      only a fill still gets the solid-plus-ring treatment (FR-041) and gets
 *      it from its own colour rather than from a hash entry it no longer uses.
 *
 * Then the pre-existing hash-derived ring for unknown/plugin types (#543).
 *
 * `type_hierarchy.ui_ring_color` is deliberately not consulted. The field was
 * declared and never populated (spec §2.8) and FR-066 leaves it dead rather
 * than reviving it: the types listing is the single source of declared colour.
 *
 * `_typeHierarchy` is consequently **unread**, and kept only so the signature
 * stays positionally parallel to `resolveTypeColor`, which does read it — every
 * call site passes the same three arguments to both. The underscore is what
 * says so from the signature, rather than leaving a reader to grep the body
 * (`docs/audit/2026-08-07-adr-053-spec1-track-b.md` P3-4).
 */
export function resolveRingColor(
  typeNames: string[],
  _typeHierarchy?: TypeHierarchyEntry[],
  declared?: DeclaredTypeColors,
): string | undefined {
  for (const name of typeNames) {
    const own = declared?.get(name);
    if (own?.ring) {
      return own.ring;
    }
    // Check explicit ring colors first
    if (subtypeRingColorMap[name]) {
      return subtypeRingColorMap[name];
    }
    if (own?.fill) {
      return darkenHex(own.fill, 0.3);
    }
  }
  // Auto-derive ring color for types not in the manual maps (#543)
  if (typeNames.length > 0 && !typeColorMap[typeNames[0]]) {
    // Plugin subtypes that inherit a base color get a hash-derived ring
    // to visually distinguish them from the base type.
    const idx = hashTypeName(typeNames[0]) % HASH_PALETTE.length;
    return darkenHex(HASH_PALETTE[idx], 0.3);
  }
  return undefined;
}

/**
 * Check whether a port represents the "Any" type (empty accepted_types).
 */
export function isAnyType(typeNames: string[]): boolean {
  return typeNames.length === 0;
}

/**
 * Get the primary display type name for a port.
 */
export function primaryTypeName(typeNames: string[]): string {
  if (typeNames.length === 0) return "Any";
  return typeNames[0];
}

/**
 * Resolve a type's *fundamental core base* — the highest ancestor in its
 * inheritance chain whose immediate base is the universal `DataObject` root
 * (#1840). For `SRSImage → Image → Array → DataObject` this is `Array`, not
 * the immediate parent `Image` and not the generic root `DataObject`.
 *
 * Returns `null` (omit the annotation) when:
 *   - the type already IS a core base (its immediate base is `DataObject`),
 *     so there is no redundant `Array (Array)`;
 *   - the type is `DataObject` itself;
 *   - the chain can't be resolved (unknown type, or a root that does not
 *     descend from `DataObject`);
 *   - a cycle is detected (defensive).
 *
 * Walks frontend-side from the existing `type_hierarchy` (a `name → base_type`
 * map), so no backend change is needed.
 */
export function resolveCoreBaseType(
  typeName: string,
  typeHierarchy?: TypeHierarchyEntry[],
): string | null {
  if (!typeName || typeName === "DataObject" || !typeHierarchy) return null;
  const baseOf = new Map<string, string>();
  for (const entry of typeHierarchy) baseOf.set(entry.name, entry.base_type ?? "");

  let current = typeName;
  const seen = new Set<string>([current]);
  while (baseOf.has(current)) {
    const parent = baseOf.get(current) as string;
    if (parent === "DataObject") {
      // `current` is the highest ancestor above DataObject — the core base.
      // Omit when it equals the displayed type (no redundant `Array (Array)`).
      return current === typeName ? null : current;
    }
    if (parent === "" || seen.has(parent)) return null; // root-not-via-DataObject / cycle
    seen.add(parent);
    current = parent;
  }
  return null; // chain left the known hierarchy → unresolved
}
