// Frontend port type-compatibility check.
//
// Mirrors :func:`scistudio.blocks.base.ports.validate_connection` so the
// canvas can flag edges that became invalid after a config change (e.g. the
// user toggled LoadData's ``core_type`` from ``Array`` to ``Text`` while a
// downstream Array-consumer was still wired). The backend only re-validates
// at workflow save / run, leaving the edge looking healthy in the meantime.
//
// Rule (matches backend ``validate_connection``):
//   - Empty ``source.accepted_types`` → Any-source, compatible with anything.
//   - Empty ``target.accepted_types`` → Any-target, compatible with anything.
//   - Otherwise compatible iff at least one source type is a subtype of any
//     target type, or vice versa, walking the ``type_hierarchy`` chain.

import type { TypeHierarchyEntry } from "../types/api";

function buildBaseLookup(typeHierarchy: TypeHierarchyEntry[] | undefined): Map<string, string> {
  const map = new Map<string, string>();
  if (!typeHierarchy) return map;
  for (const entry of typeHierarchy) {
    if (entry.name && entry.base_type) {
      map.set(entry.name, entry.base_type);
    }
  }
  return map;
}

function isSubtype(child: string, parent: string, baseLookup: Map<string, string>): boolean {
  if (child === parent) return true;
  let cursor: string | undefined = baseLookup.get(child);
  const visited = new Set<string>([child]);
  while (cursor) {
    if (cursor === parent) return true;
    if (visited.has(cursor)) return false;
    visited.add(cursor);
    cursor = baseLookup.get(cursor);
  }
  return false;
}

export function arePortTypesCompatible(
  sourceAcceptedTypes: string[],
  targetAcceptedTypes: string[],
  typeHierarchy: TypeHierarchyEntry[] | undefined,
): boolean {
  if (sourceAcceptedTypes.length === 0) return true;
  if (targetAcceptedTypes.length === 0) return true;
  const baseLookup = buildBaseLookup(typeHierarchy);
  for (const src of sourceAcceptedTypes) {
    for (const tgt of targetAcceptedTypes) {
      if (isSubtype(src, tgt, baseLookup) || isSubtype(tgt, src, baseLookup)) {
        return true;
      }
    }
  }
  return false;
}
