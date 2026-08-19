// Cascade promotion — which project-level types a promoted file drags with it.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6.1
//   FR-021 (determine the project-level type dependencies before promoting),
//   FR-022 (static import parse, resolved against the type registry and
//     classified by origin using the shared resolver),
//   FR-023 (offer them alongside the block as a single confirmed action;
//     declining still promotes, with an explicit warning),
//   FR-024 (one level deep — a type that itself imports another project-level
//     type is out of scope and MUST be **reported**, never silently missed).
//
// Where the parse runs, and why here: `pythonImports.parseImports` reads the
// source text the frontend already holds (the editor buffer, or
// `GET /api/blocks/{type}/source`), and the classification step reads `origin`
// straight off `GET /api/types/` — which the backend filled in with the FR-003
// shared resolver. So the *classification* FR-022 requires is the shared
// resolver's own answer, transported rather than re-derived; only the import
// extraction is local. Re-deriving origin on the client would have created the
// second supply point this spec exists to remove.
//
// FR-024's residue is the reason the second level is walked at all. The spec
// accepts a one-level cascade *precisely because* the remainder is visible, so
// the second level is resolved and reported even though it is never promoted.
// Dropping the walk would turn an accepted limit into a silent failure.

import type { TypeSummary } from "../../types/api";

import { importedModuleRoots, importedSymbols, parseImports } from "./pythonImports";

/** The file-stem a drop-in type is importable by, or `null` when unresolvable. */
export function typeModuleName(type: TypeSummary): string | null {
  if (!type.file_path) return null;
  const base = type.file_path.split(/[\\/]/).pop() ?? "";
  const stem = base.replace(/\.py$/i, "");
  return stem.length > 0 && stem !== base ? stem : null;
}

/** One project-level type a promoted file depends on. */
export interface TypeDependency {
  type: TypeSummary;
  /** Module stem the file imports it by, when it has one. */
  module: string | null;
}

/**
 * Project-level types *source* imports.
 *
 * Two resolutions are accepted and both are needed. The module stem is the
 * normal one — a drop-in type is importable by its file name, so
 * `from spectrum import Spectrum` names `{project}/types/spectrum.py`. The
 * registered class name covers the file whose stem does not match the type it
 * declares (`types/my_types.py` declaring `Spectrum`), which the module test
 * alone would miss. Over-reporting here costs the user one declinable
 * checkbox; under-reporting silently ships a block that cannot load elsewhere,
 * which is the failure FR-021 exists to prevent.
 */
export function projectTypeDependencies(
  source: string,
  catalogue: readonly TypeSummary[],
): TypeDependency[] {
  const imports = parseImports(source);
  const modules = importedModuleRoots(imports);
  const symbols = importedSymbols(imports);
  const found: TypeDependency[] = [];
  for (const type of catalogue) {
    if (type.origin !== "project") continue;
    const module = typeModuleName(type);
    const byModule = module !== null && modules.has(module);
    const byName = symbols.has(type.name);
    if (byModule || byName) {
      found.push({ type, module });
    }
  }
  return found.sort((a, b) => a.type.name.localeCompare(b.type.name));
}

/**
 * A project-level type reached only through another project-level type.
 *
 * FR-024 puts this out of scope for promotion and in scope for reporting: the
 * user is told the name, and which of the promoted types imports it, so the
 * residue of the one-level limit is a sentence they can act on rather than a
 * block that mysteriously fails in the next project.
 */
export interface SecondLevelDependency {
  /** The type that is NOT promoted. */
  type: TypeSummary;
  /** The first-level dependency whose imports reached it. */
  via: TypeSummary;
}

/** Reads one project-level type's source text. */
export type TypeSourceReader = (type: TypeSummary) => Promise<string>;

export interface CascadePlan {
  /** First-level project types — promotable alongside the item (FR-023). */
  dependencies: TypeDependency[];
  /** Second-level project types — reported, never promoted (FR-024). */
  secondLevel: SecondLevelDependency[];
  /**
   * First-level types whose own source could not be read, so their second
   * level is unknown. Reported for the same reason FR-024's residue is: an
   * unanswered question the user can see beats one they cannot.
   */
  unreadable: TypeSummary[];
}

/**
 * Resolve the cascade for *source*: its project-level type dependencies, and
 * the second level those dependencies reach.
 *
 * A first-level type whose source cannot be read is recorded in `unreadable`
 * rather than failing the plan — its own promotion still works (the promotion
 * write reads the file server-side), and only the FR-024 report is degraded.
 */
export async function resolveCascade(
  source: string,
  catalogue: readonly TypeSummary[],
  readTypeSource: TypeSourceReader,
): Promise<CascadePlan> {
  const dependencies = projectTypeDependencies(source, catalogue);
  const firstLevelNames = new Set(dependencies.map((entry) => entry.type.name));
  const secondLevel: SecondLevelDependency[] = [];
  const unreadable: TypeSummary[] = [];
  const seen = new Set<string>();

  for (const entry of dependencies) {
    let nested: string;
    try {
      nested = await readTypeSource(entry.type);
    } catch {
      unreadable.push(entry.type);
      continue;
    }
    for (const deeper of projectTypeDependencies(nested, catalogue)) {
      if (deeper.type.name === entry.type.name) continue;
      if (firstLevelNames.has(deeper.type.name)) continue;
      const key = `${entry.type.name}→${deeper.type.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      secondLevel.push({ type: deeper.type, via: entry.type });
    }
  }

  return { dependencies, secondLevel, unreadable };
}
