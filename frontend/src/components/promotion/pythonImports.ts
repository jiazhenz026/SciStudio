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
//
// "Recognisable without a full grammar" is only true of a source that has lost
// its string literals first — a `(` inside a string is not a bracket, and a
// scanner that counts it as one stops finding imports altogether. See
// `withoutLiteralsAndComments`.

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
 * Remove every string literal and every comment, keeping the line structure.
 *
 * One pass, because the three things it removes can only be told apart by
 * reading the file in order. A `#` inside a literal is not a comment, a quote
 * inside a comment does not open a literal, and — the case this scanner exists
 * for — a bracket inside a literal is not a bracket:
 *
 * ```python
 * pattern = "("
 * from spectrum import Spectrum
 * ```
 *
 * A delimiter counter that does not know about literals reads that `(` as an
 * open bracket, joins every following line into one logical line, and the
 * import regexes — anchored at the start of a statement — then match nothing.
 * The consequence is precisely what FR-024 forbids: cascade promotion moves
 * the block **without** its project-local type, silently, and the promoted
 * block fails in every other project with no warning anywhere. Removing
 * literals before counting is what makes that impossible rather than unlikely.
 *
 * Docstrings are removed by the same pass, for the reason they always were:
 * they routinely contain example code (`from spectrum import Spectrum` in a
 * block's own docstring is the obvious case) and counting those as real
 * imports would offer a cascade for a dependency the file does not have.
 * Newlines inside a triple-quoted literal are preserved so the statements
 * around it stay separate lines; a single-quoted literal can only contain a
 * newline as a backslash continuation, which genuinely continues the logical
 * line, so those are dropped with the rest of it.
 *
 * A backslash escapes the next character in every literal, raw ones included:
 * `r"\""` does not terminate at the middle quote even though the backslash
 * survives into the value, so no prefix handling is needed to get termination
 * right. The one form this does not model is a 3.12+ f-string reusing its own
 * quote character inside a replacement field; consistent with the rest of this
 * module, the mis-parse can only lose an import and never invent one.
 */
function withoutLiteralsAndComments(source: string): string {
  let out = "";
  let index = 0;
  while (index < source.length) {
    const char = source[index];
    if (char === "#") {
      const newline = source.indexOf("\n", index);
      index = newline === -1 ? source.length : newline;
      continue;
    }
    if (char !== "'" && char !== '"') {
      out += char;
      index += 1;
      continue;
    }
    const triple = source.slice(index, index + 3);
    const delimiter = triple === "'''" || triple === '"""' ? triple : char;
    let cursor = index + delimiter.length;
    while (cursor < source.length) {
      if (source[cursor] === "\\") {
        cursor += 2;
        continue;
      }
      // An unterminated single-quoted literal ends at the newline rather than
      // swallowing the rest of the file — a syntax error must not decide what
      // the parse above it sees.
      if (source[cursor] === "\n" && delimiter.length === 1) break;
      if (source.startsWith(delimiter, cursor)) {
        cursor += delimiter.length;
        break;
      }
      cursor += 1;
    }
    if (delimiter.length === 3) {
      out += source.slice(index, cursor).replace(/[^\n]/g, "");
    }
    index = cursor;
  }
  return out;
}

/**
 * Join backslash and parenthesis continuations into logical lines.
 *
 * `from spectrum import (\n    Spectrum,\n    Trace,\n)` is one statement, and
 * a line-at-a-time reader would see three fragments and understand none of
 * them. The delimiters are counted on a source that has already lost its
 * literals and comments, so only real brackets are counted.
 */
function logicalLines(source: string): string[] {
  const lines = withoutLiteralsAndComments(source).split(/\r?\n/);
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
