// Shared promotion test fixtures (ADR-053 §6, §6.1, §8).
//
// One factory per summary shape so the action, component, and flow tests
// cannot drift on what a project-tier item actually looks like on the wire —
// notably that `origin` is the FR-019 condition and `file_path` is what makes
// a type's source locatable.

import type { BlockSummary, TypeSummary } from "../../../types/api";

export function makeBlock(
  overrides: Partial<BlockSummary> & { type_name: string; name: string },
): BlockSummary {
  return {
    name: overrides.name,
    type_name: overrides.type_name,
    base_category: overrides.base_category ?? "process",
    subcategory: overrides.subcategory ?? "",
    description: overrides.description ?? "A block",
    version: "0.1.0",
    input_ports: overrides.input_ports ?? [],
    output_ports: overrides.output_ports ?? [],
    source: overrides.source,
    origin: overrides.origin,
    package_name: overrides.package_name,
  };
}

export function makeType(overrides: Partial<TypeSummary> & { name: string }): TypeSummary {
  return {
    name: overrides.name,
    base_type: overrides.base_type ?? "DataObject",
    description: overrides.description ?? "",
    origin: overrides.origin ?? "core",
    file_path: overrides.file_path ?? null,
    // #2025: package attribution (B6) landed in parallel with this fixture and
    // is required on TypeSummary. null is what every non-package tier reports.
    package_name: overrides.package_name ?? null,
    ui_color: overrides.ui_color ?? null,
    ui_ring_color: overrides.ui_ring_color ?? null,
    load_extensions: overrides.load_extensions ?? [],
    save_extensions: overrides.save_extensions ?? [],
  };
}

/** A project-tier drop-in type at `{project}/types/<stem>.py`. */
export function projectType(name: string, stem: string): TypeSummary {
  return makeType({
    name,
    origin: "project",
    file_path: `/home/dev/proj/types/${stem}.py`,
  });
}
