/**
 * SciStudio plot-render completions for Monaco.
 *
 * Monaco only knows generic Python/R tokens here; it cannot infer the
 * preview-side ``context`` object that SciStudio injects into
 * ``plots/<id>/render.py`` and ``plots/<id>/render.R``. Keep this scoped to
 * plot render files so normal project scripts are not polluted with plot-only
 * helpers.
 */

export interface PlotCompletionSpec {
  label: string;
  insertText: string;
  detail: string;
  documentation: string;
  kind: "function" | "property";
}

interface MonacoPosition {
  lineNumber: number;
  column: number;
}

interface MonacoWordRange {
  startColumn: number;
  endColumn: number;
}

interface MonacoModel {
  uri?: {
    path?: string;
    toString?: () => string;
  };
  getLineContent?: (lineNumber: number) => string;
  getWordUntilPosition?: (position: MonacoPosition) => MonacoWordRange;
}

interface MonacoCompletionRange {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
}

interface MonacoCompletionItem {
  label: string;
  kind: number;
  insertText: string;
  insertTextRules?: number;
  detail: string;
  documentation: string;
  range?: MonacoCompletionRange;
}

interface MonacoCompletionProvider {
  triggerCharacters?: string[];
  provideCompletionItems: (
    model: MonacoModel,
    position: MonacoPosition,
  ) => { suggestions: MonacoCompletionItem[] };
}

interface MonacoLanguages {
  CompletionItemKind?: {
    Function?: number;
    Property?: number;
  };
  CompletionItemInsertTextRule?: {
    InsertAsSnippet?: number;
  };
  registerCompletionItemProvider?: (
    language: string,
    provider: MonacoCompletionProvider,
  ) => { dispose: () => void };
}

interface MonacoNamespace {
  languages?: MonacoLanguages;
  __scistudioPlotCompletionsRegistered?: boolean;
}

const PYTHON_CONTEXT_COMPLETIONS: PlotCompletionSpec[] = [
  {
    label: "to_dataframe",
    insertText: "to_dataframe(collection, max_rows=${1:10000})",
    detail: "SciStudio plot helper",
    documentation: "Return a bounded pandas DataFrame from the bound input collection.",
    kind: "function",
  },
  {
    label: "items",
    insertText: "items(collection, max_items=${1:5})",
    detail: "SciStudio plot helper",
    documentation: "Iterate over a bounded list of input data references.",
    kind: "function",
  },
  {
    label: "plt",
    insertText: "plt",
    detail: "SciStudio plot helper",
    documentation: "matplotlib.pyplot configured with the non-interactive Agg backend.",
    kind: "property",
  },
  {
    label: "save_figure",
    insertText: 'save_figure(${1:fig}, "${2:figure.svg}")',
    detail: "SciStudio plot helper",
    documentation: "Save a matplotlib figure as PNG, JPEG, SVG, or PDF and return the path.",
    kind: "function",
  },
  {
    label: "save_plot",
    insertText: 'save_plot(${1:fig}, "${2:figure.svg}")',
    detail: "SciStudio plot helper",
    documentation: "Alias for save_figure, matching the R helper name.",
    kind: "function",
  },
];

const R_CONTEXT_COMPLETIONS: PlotCompletionSpec[] = [
  {
    label: "to_dataframe",
    insertText: "to_dataframe(collection, max_rows = ${1:10000})",
    detail: "SciStudio plot helper",
    documentation: "Return a bounded data.frame from the bound input collection.",
    kind: "function",
  },
  {
    label: "save_plot",
    insertText: 'save_plot(${1:p}, "${2:figure.pdf}")',
    detail: "SciStudio plot helper",
    documentation: "Save a ggplot, grob, or base-R plot as PNG, JPEG, SVG, or PDF.",
    kind: "function",
  },
  {
    label: "save_figure",
    insertText: 'save_figure(${1:p}, "${2:figure.svg}")',
    detail: "SciStudio plot helper",
    documentation: "Alias for save_plot, matching the Python helper name.",
    kind: "function",
  },
];

export function isPlotRenderFilePath(filePath: string): boolean {
  const normalized = filePath.replace(/\\/g, "/").split(/[?#]/, 1)[0].toLowerCase();
  return /(?:^|\/)plots\/[^/]+\/render\.(py|r)$/.test(normalized);
}

export function suggestPlotContextCompletions(args: {
  language: string;
  filePath: string;
  linePrefix: string;
}): PlotCompletionSpec[] {
  if (!isPlotRenderFilePath(args.filePath)) return [];
  if (args.language === "python") {
    return /\bcontext\.[A-Za-z_][A-Za-z0-9_]*$|\bcontext\.$/.test(args.linePrefix)
      ? PYTHON_CONTEXT_COMPLETIONS
      : [];
  }
  if (args.language === "r") {
    return /\bcontext\$[A-Za-z_.][A-Za-z0-9_.]*$|\bcontext\$$/.test(args.linePrefix)
      ? R_CONTEXT_COMPLETIONS
      : [];
  }
  return [];
}

export function registerPlotCompletions(monaco: MonacoNamespace): void {
  if (monaco.__scistudioPlotCompletionsRegistered) return;
  const register = monaco.languages?.registerCompletionItemProvider;
  if (!register) return;

  register("python", buildProvider(monaco, "python", ["."]));
  register("r", buildProvider(monaco, "r", ["$"]));
  monaco.__scistudioPlotCompletionsRegistered = true;
}

function buildProvider(
  monaco: MonacoNamespace,
  language: "python" | "r",
  triggerCharacters: string[],
): MonacoCompletionProvider {
  return {
    triggerCharacters,
    provideCompletionItems(model, position) {
      const filePath = modelPath(model);
      const linePrefix = (model.getLineContent?.(position.lineNumber) ?? "").slice(
        0,
        Math.max(0, position.column - 1),
      );
      const suggestions = suggestPlotContextCompletions({ language, filePath, linePrefix });
      const range = completionRange(model, position);
      return {
        suggestions: suggestions.map((spec) => toMonacoCompletion(monaco, spec, range)),
      };
    },
  };
}

function modelPath(model: MonacoModel): string {
  const uri = model.uri;
  if (!uri) return "";
  if (typeof uri.path === "string" && uri.path.length > 0) return uri.path;
  const text = uri.toString?.();
  return typeof text === "string" ? text : "";
}

function completionRange(
  model: MonacoModel,
  position: MonacoPosition,
): MonacoCompletionRange | undefined {
  const word = model.getWordUntilPosition?.(position);
  if (!word) return undefined;
  return {
    startLineNumber: position.lineNumber,
    startColumn: word.startColumn,
    endLineNumber: position.lineNumber,
    endColumn: word.endColumn,
  };
}

function toMonacoCompletion(
  monaco: MonacoNamespace,
  spec: PlotCompletionSpec,
  range: MonacoCompletionRange | undefined,
): MonacoCompletionItem {
  const kinds = monaco.languages?.CompletionItemKind;
  const snippetRule = monaco.languages?.CompletionItemInsertTextRule?.InsertAsSnippet;
  return {
    label: spec.label,
    kind: spec.kind === "property" ? (kinds?.Property ?? 10) : (kinds?.Function ?? 1),
    insertText: spec.insertText,
    insertTextRules: snippetRule,
    detail: spec.detail,
    documentation: spec.documentation,
    range,
  };
}
