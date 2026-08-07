// Static extraction of a Python module's import statements.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6.1 FR-022 — dependency
// detection parses the block's imports **statically** and resolves each
// imported name against the type registry. Static parsing is sufficient
// because after the §5 drop-in import fix (#2022) a block expresses a type
// dependency as a real import statement rather than a runtime lookup.
//
// "Statically" is the load-bearing word: nothing here executes, imports, or
// otherwise trusts the file. It reads text and returns the import statements
// it found, and every consumer treats the result as a candidate list that is
// then resolved against the registry — never as an authority on what exists.
//
// Why a hand-rolled scanner rather than a Python parser in the browser: the
// only questions FR-022 asks are "which modules does this file import" and
// "which names does it bind from them". Both are answered by the statement
// forms below, all of which are recognisable without a full grammar, and the
// alternative — shipping a Python parser to the renderer, or adding a backend
// endpoint for it — buys nothing the registry resolution step does not already
// re-check. The scanner is deliberately conservative: anything it cannot parse
// is skipped rather than guessed at, and a missed import can only ever cause a
// dependency to be *reported* as unpromoted rather than silently promoted.

/** One parsed import statement. */
export interface ParsedImport {
  /**
   * The module the statement names, dotted form, leading relative dots
   * stripped. `import a.b` and `from a.b import C` both yield `"a.b"`.
   * Empty for a bare relative `from . import x`.
   */
  module: string;
  /**
   * Names bound from the module by a `from … import` statement, before any
   * `as` alias. Empty for a plain `import …` and for `from … import *`.
   */
  names: string[];
}

/**
 * Replace triple-quoted blocks with equivalent blank lines.
 *
 * Docstrings routinely contain example code (`from spectrum import Spectrum`
 * in a block's own docstring is the obvious case), and counting those as real
 * imports would offer a cascade for a dependency the file does not have.
 * Newlines are preserved so nothing downstream has to care that text was
 * removed.
 */
function stripTripleQuoted(source: string): string {
  let out = "";
  let index = 0;
  while (index < source.length) {
    const remaining = source.slice(index);
    const match = /^(?:'''|""")/.exec(remaining);
    if (!match) {
      out += source[index];
      index += 1;
      continue;
    }
    const delimiter = match[0];
    const closing = source.indexOf(delimiter, index + delimiter.length);
    const end = closing === -1 ? source.length : closing + delimiter.length;
    const swallowed = source.slice(index, end);
    out += swallowed.replace(/[^\n]/g, "");
    index = end;
  }
  return out;
}

/** Drop a trailing `#` comment from one logical line. */
function stripComment(line: string): string {
  const hash = line.indexOf("#");
  return hash === -1 ? line : line.slice(0, hash);
}

/**
 * Join backslash and parenthesis continuations into logical lines.
 *
 * `from spectrum import (\n    Spectrum,\n    Trace,\n)` is one statement, and
 * a line-at-a-time reader would see three fragments and understand none of
 * them.
 */
function logicalLines(source: string): string[] {
  const lines = stripTripleQuoted(source).split(/\r?\n/).map(stripComment);
  const out: string[] = [];
  let buffer = "";
  let depth = 0;
  for (const line of lines) {
    const trimmedEnd = line.replace(/\s+$/, "");
    const continues = trimmedEnd.endsWith("\\");
    const body = continues ? trimmedEnd.slice(0, -1) : trimmedEnd;
    buffer = buffer ? `${buffer} ${body.trim()}` : body;
    for (const char of body) {
      if (char === "(" || char === "[" || char === "{") depth += 1;
      if (char === ")" || char === "]" || char === "}") depth = Math.max(0, depth - 1);
    }
    if (continues || depth > 0) {
      continue;
    }
    out.push(buffer);
    buffer = "";
  }
  if (buffer) out.push(buffer);
  return out;
}

const IMPORT_RE = /^\s*import\s+(.+)$/;
const FROM_RE = /^\s*from\s+([.\w]+)\s+import\s+(.+)$/;

/** `Spectrum as S` → `Spectrum`; `*` and empty entries drop out. */
function bareNames(clause: string): string[] {
  return clause
    .replace(/[()]/g, " ")
    .split(",")
    .map((entry) =>
      entry
        .trim()
        .split(/\s+as\s+/)[0]
        .trim(),
    )
    .filter((name) => name.length > 0 && name !== "*" && /^[A-Za-z_]\w*$/.test(name));
}

/** `a.b as x, c` → `["a.b", "c"]`. */
function bareModules(clause: string): string[] {
  return clause
    .split(",")
    .map((entry) =>
      entry
        .trim()
        .split(/\s+as\s+/)[0]
        .trim(),
    )
    .filter((name) => name.length > 0 && /^[A-Za-z_][\w.]*$/.test(name));
}

/**
 * Parse every import statement in *source*.
 *
 * Indented imports count: a drop-in block that imports its type inside a
 * `try:` block or inside a method still depends on that type, and treating
 * only module-level imports as real would miss exactly the defensive-import
 * style that drop-in authors write.
 */
export function parseImports(source: string): ParsedImport[] {
  const parsed: ParsedImport[] = [];
  for (const line of logicalLines(source)) {
    const from = FROM_RE.exec(line);
    if (from) {
      parsed.push({
        module: from[1].replace(/^\.+/, ""),
        names: bareNames(from[2]),
      });
      continue;
    }
    const plain = IMPORT_RE.exec(line);
    if (plain) {
      for (const module of bareModules(plain[1])) {
        parsed.push({ module, names: [] });
      }
    }
  }
  return parsed;
}

/**
 * Top-level module names an import list reaches.
 *
 * Drop-in type directories join `sys.path` as roots (spec §5), so a drop-in
 * type is always addressed by its top-level file stem — `spectrum` for
 * `{project}/types/spectrum.py`. The first dotted segment is therefore the
 * only segment that can ever name one.
 */
export function importedModuleRoots(imports: readonly ParsedImport[]): Set<string> {
  const roots = new Set<string>();
  for (const entry of imports) {
    const root = entry.module.split(".")[0];
    if (root) roots.add(root);
  }
  return roots;
}

/** Every name bound by a `from … import` statement, aliases resolved. */
export function importedSymbols(imports: readonly ParsedImport[]): Set<string> {
  const symbols = new Set<string>();
  for (const entry of imports) {
    for (const name of entry.names) symbols.add(name);
  }
  return symbols;
}
