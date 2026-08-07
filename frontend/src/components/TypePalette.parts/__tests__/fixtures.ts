// Shared Data types tab test fixtures (ADR-053 §9.2).
//
// One `TypeSummary` factory for the model, component, and colour-parity tests
// so the three cannot drift on what the B2 listing contract actually sends —
// notably that `load_extensions` / `save_extensions` are always present and
// that both colour fields are `null`, not absent, when nothing is declared.

import type { TypeSummary } from "../../../types/api";

export function makeType(overrides: Partial<TypeSummary> & { name: string }): TypeSummary {
  return {
    name: overrides.name,
    base_type: overrides.base_type ?? "DataObject",
    description: overrides.description ?? "",
    origin: overrides.origin ?? "core",
    file_path: overrides.file_path ?? null,
    ui_color: overrides.ui_color ?? null,
    ui_ring_color: overrides.ui_ring_color ?? null,
    load_extensions: overrides.load_extensions ?? [],
    save_extensions: overrides.save_extensions ?? [],
  };
}
