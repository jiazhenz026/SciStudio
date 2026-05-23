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

/**
 * Darken a hex color by a given amount (0-1) for ring color derivation.
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
 * Resolve the fill color for a port given its accepted_types list and
 * optional type hierarchy from the schema.
 */
export function resolveTypeColor(
  typeNames: string[],
  typeHierarchy?: TypeHierarchyEntry[],
): string {
  for (const name of typeNames) {
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
 * Resolve the ring (border) color for a subtype port. Returns `undefined`
 * for base types that should not have a contrasting ring.
 */
export function resolveRingColor(
  typeNames: string[],
  typeHierarchy?: TypeHierarchyEntry[],
): string | undefined {
  for (const name of typeNames) {
    // Check explicit ring colors first
    if (subtypeRingColorMap[name]) {
      return subtypeRingColorMap[name];
    }
    // Check backend-supplied ui_ring_color
    if (typeHierarchy) {
      const entry = typeHierarchy.find((t) => t.name === name);
      if (entry?.ui_ring_color) {
        return entry.ui_ring_color;
      }
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
