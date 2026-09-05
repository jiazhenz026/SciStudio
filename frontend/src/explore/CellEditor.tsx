/**
 * ADR-054 spec 4 (T-004) — one Monaco editor per visible cell, and the static
 * text every other cell renders as (FR-008).
 *
 * Two components, because the shell needs exactly two states for a cell body
 * and nothing between them:
 *
 *   - `CellEditor` mounts the Monaco editor the bundle already carries. It is
 *     rendered only for the cells the shell says are on screen.
 *   - `StaticCellSource` renders the same source as highlighted, selectable
 *     text with no editor behind it. Every other cell is one of these.
 *
 * **Why this split is the first task and not an optimisation.** Spec §4.5
 * names editor cost as the first risk: a two-hundred-cell notebook with a
 * Monaco instance per cell is not slow, it is unusable — each instance carries
 * its own model, its own tokenizer worker traffic, and its own DOM. A hundred
 * static blocks are a hundred `<pre>`s.
 *
 * **The editor holds no truth.** `value` is handed in and every keystroke is
 * handed back; the draft lives in `NotebookShell`'s state, so an editor that is
 * unmounted by a scroll and remounted by a scroll back finds its text waiting
 * for it. Nothing in this module reads the store, calls the API, or decides
 * when a cell is saved.
 *
 * The lazy `import()` of `@monaco-editor/react` mirrors `CodeEditor.tsx`: the
 * module is ~600 KB and must not be on the workflow canvas's cold-start path.
 * The import is module-cached, so only the first cell on screen pays for it.
 */

import { useEffect, useMemo, useState } from "react";

/**
 * The subset of `@monaco-editor/react`'s props this module uses.
 *
 * Declared inline for the same reason `CodeEditor.tsx` declares it inline: a
 * type import at module scope is erased by TypeScript, but writing it out keeps
 * the lazy-loading intent legible to the next reader.
 */
interface EditorComponentProps {
  height?: string | number;
  width?: string | number;
  theme?: string;
  language?: string;
  value?: string;
  path?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  options?: Record<string, any>;
  onChange?: (value: string | undefined) => void;
}

type EditorComponent = React.ComponentType<EditorComponentProps>;

/**
 * The one lazy load of `@monaco-editor/react`, shared by every cell.
 *
 * Module-level rather than per component, for two reasons that both matter in a
 * notebook: the second cell to come on screen must not re-enter the loader, and
 * a cell scrolled back into view must get its editor **synchronously** — a
 * per-instance load would show "loading" for a frame on every scroll, which in
 * a virtualised list is every few rows.
 */
let loadedEditor: EditorComponent | null = null;
let editorLoad: Promise<EditorComponent> | null = null;

function loadEditorComponent(): Promise<EditorComponent> {
  if (!editorLoad) {
    editorLoad = import("@monaco-editor/react").then((mod) => {
      loadedEditor = mod.default as unknown as EditorComponent;
      return loadedEditor;
    });
  }
  return editorLoad;
}

/** Pixel height of one Monaco line at the size the cells use. */
const LINE_HEIGHT = 19;
/** Room for the editor's own padding, so the last line is not clipped. */
const EDITOR_PADDING = 14;
/** A cell taller than this scrolls inside its own editor rather than the pane. */
const MAX_EDITOR_HEIGHT = 480;
const MIN_EDITOR_HEIGHT = LINE_HEIGHT + EDITOR_PADDING;

/** The editor is sized to its content: a three-line cell is three lines tall. */
export function editorHeightFor(source: string): number {
  const lines = source.length === 0 ? 1 : source.split("\n").length;
  return Math.min(
    Math.max(lines * LINE_HEIGHT + EDITOR_PADDING, MIN_EDITOR_HEIGHT),
    MAX_EDITOR_HEIGHT,
  );
}

export interface CellEditorProps {
  /** The cell this editor is bound to; also Monaco's model path. */
  cellId: string;
  /** `python` for a code cell, `markdown` for a markdown cell being edited. */
  language: string;
  /** The draft if the person has typed, otherwise the runtime's source. */
  value: string;
  /** A disabled cell is read-only; the toggle is the way to change that. */
  readOnly?: boolean;
  /** Every keystroke. The shell decides what to do with it. */
  onChange: (value: string) => void;
  /** Told when the person is in this cell, so the shell keeps it mounted. */
  onFocus?: () => void;
  onBlur?: () => void;
}

/**
 * One Monaco editor, for one cell that is on screen.
 *
 * While the module is still loading, the source renders as static text rather
 * than as a blank box — the person can read the cell during the one import
 * that the whole notebook pays for.
 */
export function CellEditor({
  cellId,
  language,
  value,
  readOnly = false,
  onChange,
  onFocus,
  onBlur,
}: CellEditorProps) {
  // Already loaded — which is every cell after the first — mounts with the
  // editor rather than with a loading frame.
  const [EditorComponent, setEditorComponent] = useState<EditorComponent | null>(
    () => loadedEditor,
  );

  useEffect(() => {
    if (loadedEditor) return;
    let cancelled = false;
    void loadEditorComponent().then((component) => {
      if (!cancelled) setEditorComponent(() => component);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const height = editorHeightFor(value);

  return (
    <div
      className="rounded border border-stone-200 bg-white"
      data-testid={`explore-cell-editor-${cellId}`}
      onFocus={onFocus}
      onBlur={onBlur}
    >
      {EditorComponent ? (
        <EditorComponent
          height={height}
          width="100%"
          language={language}
          value={value}
          path={`explore-cell/${cellId}`}
          options={{
            readOnly,
            automaticLayout: true,
            fontFamily: "Consolas, Menlo, monospace",
            fontSize: 12,
            lineHeight: LINE_HEIGHT,
            lineNumbers: "off",
            folding: false,
            minimap: { enabled: false },
            overviewRulerLanes: 0,
            scrollBeyondLastLine: false,
            renderLineHighlight: "none",
            tabSize: 4,
            insertSpaces: true,
            wordWrap: "on",
          }}
          onChange={(next) => onChange(next ?? "")}
        />
      ) : (
        <StaticCellSource cellId={cellId} language={language} source={value} loading />
      )}
    </div>
  );
}

// -- the static half --------------------------------------------------------

type TokenKind = "comment" | "string" | "keyword" | "number" | "plain";

interface SourceToken {
  kind: TokenKind;
  text: string;
}

/**
 * The Python vocabulary the static view colours.
 *
 * Deliberately not a parser. A cell that is not being edited needs to be
 * *readable at a glance* — comments, strings, keywords and numbers apart from
 * everything else — and reaching for Monaco's tokenizer to get more would load
 * the editor this whole module exists to avoid loading.
 */
const PYTHON_TOKENS =
  /(#[^\n]*)|('''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*")|\b(0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b|\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b/g;

/**
 * Split Python source into coloured runs.
 *
 * Exported because the highlighting is the one thing in the static view worth
 * asserting on its own: a swapped-out cell that rendered its source as one grey
 * block would technically satisfy FR-008 and would still be a worse notebook.
 */
export function highlightPython(source: string): SourceToken[] {
  const tokens: SourceToken[] = [];
  let cursor = 0;
  // `exec` in a loop rather than `matchAll`, so an unterminated construct
  // simply fails to match and falls through as plain text instead of
  // consuming the rest of the cell.
  PYTHON_TOKENS.lastIndex = 0;
  let match = PYTHON_TOKENS.exec(source);
  while (match !== null) {
    if (match.index > cursor) {
      tokens.push({ kind: "plain", text: source.slice(cursor, match.index) });
    }
    const kind: TokenKind = match[1]
      ? "comment"
      : match[2]
        ? "string"
        : match[3]
          ? "number"
          : "keyword";
    tokens.push({ kind, text: match[0] });
    cursor = match.index + match[0].length;
    match = PYTHON_TOKENS.exec(source);
  }
  if (cursor < source.length) {
    tokens.push({ kind: "plain", text: source.slice(cursor) });
  }
  return tokens;
}

const TOKEN_CLASS: Record<TokenKind, string> = {
  comment: "text-stone-400 italic",
  string: "text-emerald-700",
  keyword: "text-violet-700",
  number: "text-amber-700",
  plain: "text-stone-700",
};

export interface StaticCellSourceProps {
  cellId: string;
  language: string;
  source: string;
  /** `true` while the editor module is still on its way for this cell. */
  loading?: boolean;
}

/**
 * A cell that is off screen: its source, highlighted, with no editor behind it.
 *
 * `data-editor-mounted="false"` is what `NotebookShell.test.tsx` counts. It is
 * on the row rather than here, but the pairing is the contract: exactly one of
 * these two components renders a cell's body.
 */
export function StaticCellSource({ cellId, language, source, loading }: StaticCellSourceProps) {
  const tokens = useMemo(
    () =>
      language === "python" ? highlightPython(source) : [{ kind: "plain" as const, text: source }],
    [language, source],
  );
  return (
    <pre
      className="overflow-x-auto rounded border border-stone-200 bg-white px-3 py-2 font-mono text-[12px] leading-[19px] text-stone-700 scrollbar-thin"
      data-testid={`explore-cell-static-${cellId}`}
      data-loading={loading ? "true" : "false"}
    >
      <code>
        {tokens.map((token, index) => (
          // The index is the token's identity here: the list is regenerated
          // whole on every source change and never reordered.
          // eslint-disable-next-line react/no-array-index-key
          <span className={TOKEN_CLASS[token.kind]} key={index}>
            {token.text}
          </span>
        ))}
      </code>
    </pre>
  );
}

export default CellEditor;
