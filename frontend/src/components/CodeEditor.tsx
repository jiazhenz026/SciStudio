/**
 * ADR-036 §3.1 / §3.3 / §3.7 — Monaco-backed code editor for file tabs.
 *
 * Phase 2B (I36b) replaces the skeleton placeholder with a real Monaco
 * mount. The Monaco React module (~600 KB) is imported dynamically inside
 * an ``useEffect`` so that the workflow-canvas cold start is not affected
 * — mirrors the xterm lazy-import pattern at ``TerminalView.tsx:76-88``.
 *
 * Lint pipeline:
 *   - On every content change, schedule a 600 ms debounced POST to
 *     ``/api/lint/python`` (only when ``tab.language === "python"``).
 *   - Convert the diagnostics into Monaco markers via
 *     ``monaco.editor.setModelMarkers(model, "ruff", markers)``.
 *
 * Save UX:
 *   - Ctrl+S inside the editor host fires ``onSave``. The 800 ms debounced
 *     auto-save loop lives in ``App.tsx`` (mirrors the canvas auto-save
 *     loop at ``App.tsx:478-487``); this component only proxies dirty
 *     state via ``onContentChange``.
 *
 * Edge cases:
 *   - Container unmount mid-load: bail with the cancelled flag (same as
 *     TerminalView).
 *   - ``tab.readOnly`` flips at runtime → ``editor.updateOptions({readOnly})``.
 *   - ``tab.language`` flips → ``monaco.editor.setModelLanguage(model, lang)``.
 */

import { useEffect, useRef, useState } from "react";

import type { FileTab } from "../store/types";

export interface CodeEditorProps {
  tab: FileTab;
  /** Called on every content change. App.tsx debounces auto-save here. */
  onContentChange: (content: string) => void;
  /** Called when the user invokes save (Ctrl+S inside the editor). */
  onSave: () => void;
}

interface LintDiagnostic {
  line: number;
  column: number;
  end_line: number;
  end_column: number;
  code: string;
  severity: "error" | "warning" | "info" | string;
  message: string;
}

interface LintResponse {
  diagnostics: LintDiagnostic[];
  note?: string;
}

const LINT_DEBOUNCE_MS = 600;

/**
 * Map a ruff severity to Monaco's MarkerSeverity numeric enum:
 *   Hint = 1, Info = 2, Warning = 4, Error = 8.
 * We avoid importing monaco at module scope so the editor stays lazy.
 */
function severityToMarkerSeverity(severity: string): number {
  switch (severity) {
    case "error":
      return 8;
    case "warning":
      return 4;
    case "info":
      return 2;
    default:
      return 1;
  }
}

export function CodeEditor({ tab, onContentChange, onSave }: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Lazy-loaded Monaco React module + the editor + monaco instances.
  // We hold them in refs so callback closures can reach the latest value
  // without re-rendering.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const monacoRef = useRef<any>(null);
  const lintTimerRef = useRef<number | null>(null);

  // Keep the most recent callbacks in refs so the editor's onChange /
  // onMount handlers (registered once at mount time) always see the
  // latest props without triggering a remount.
  const onContentChangeRef = useRef(onContentChange);
  const onSaveRef = useRef(onSave);
  onContentChangeRef.current = onContentChange;
  onSaveRef.current = onSave;

  // Holds the lazy-loaded React Editor component once the dynamic import
  // resolves. Until then we render a placeholder so the workflow canvas
  // cold-start is not weighed down by Monaco's bundle.
  const [EditorComponent, setEditorComponent] =
    useState<React.ComponentType<EditorComponentProps> | null>(null);

  // Lazy-load @monaco-editor/react. Mirrors TerminalView.tsx:76-88 — the
  // `cancelled` flag protects against unmount-mid-load.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const mod = await import("@monaco-editor/react");
      if (cancelled) return;
      // The default export is the memoised <Editor>.
      setEditorComponent(() => mod.default as unknown as React.ComponentType<EditorComponentProps>);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // When tab.readOnly flips at runtime, push the change through editor.updateOptions.
  // (Initial value is set via the <Editor options=...> prop below.)
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    try {
      editor.updateOptions({ readOnly: tab.readOnly });
    } catch {
      /* editor disposed mid-flight; ignore */
    }
  }, [tab.readOnly]);

  // When tab.language flips at runtime, swap the model's language.
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    try {
      const model = editor.getModel();
      if (model) {
        monaco.editor.setModelLanguage(model, tab.language);
      }
    } catch {
      /* ignore */
    }
  }, [tab.language]);

  // Cleanup: cancel any pending lint timer on unmount.
  useEffect(() => {
    return () => {
      if (lintTimerRef.current !== null) {
        window.clearTimeout(lintTimerRef.current);
        lintTimerRef.current = null;
      }
    };
  }, []);

  // Schedule a debounced lint POST. Called from the editor's onChange.
  function scheduleLint(content: string, language: string) {
    if (language !== "python") return;
    if (lintTimerRef.current !== null) {
      window.clearTimeout(lintTimerRef.current);
    }
    lintTimerRef.current = window.setTimeout(() => {
      lintTimerRef.current = null;
      void runLint(content);
    }, LINT_DEBOUNCE_MS);
  }

  async function runLint(content: string) {
    try {
      const response = await fetch("/api/lint/python", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, filename: tab.filePath }),
      });
      if (!response.ok) return;
      const payload = (await response.json()) as LintResponse;
      applyMarkers(payload.diagnostics ?? []);
    } catch {
      // Silent: lint is a best-effort UX affordance, not load-bearing.
    }
  }

  function applyMarkers(diagnostics: LintDiagnostic[]) {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    const markers = diagnostics.map((d) => ({
      severity: severityToMarkerSeverity(d.severity),
      startLineNumber: d.line,
      startColumn: d.column,
      endLineNumber: d.end_line,
      endColumn: d.end_column,
      message: d.message,
      code: d.code,
      source: "ruff",
    }));
    try {
      monaco.editor.setModelMarkers(model, "ruff", markers);
    } catch {
      /* ignore */
    }
  }

  // OnMount handler: stash editor + monaco; wire Ctrl+S; run an initial lint.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleEditorMount(editor: any, monaco: any) {
    editorRef.current = editor;
    monacoRef.current = monaco;
    try {
      // Ctrl/Cmd + S → onSave
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        onSaveRef.current();
      });
    } catch {
      /* older monaco builds may differ; ignore */
    }
    // Initial lint pass for the bootstrap content.
    if (tab.language === "python") {
      scheduleLint(tab.content, tab.language);
    }
  }

  // Editor onChange: forward content + schedule lint.
  function handleEditorChange(value: string | undefined) {
    const next = value ?? "";
    onContentChangeRef.current(next);
    scheduleLint(next, tab.language);
  }

  // Container Ctrl+S fallback — covers the rare case where the editor
  // hasn't mounted yet (lazy chunk still loading) but a user hits Ctrl+S.
  function handleContainerKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && event.key.toLowerCase() === "s") {
      event.preventDefault();
      onSaveRef.current();
    }
  }

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      data-testid="code-editor"
      onKeyDown={handleContainerKeyDown}
    >
      {EditorComponent ? (
        <EditorComponent
          height="100%"
          width="100%"
          theme="vs"
          language={tab.language}
          value={tab.content}
          path={tab.filePath}
          options={{
            readOnly: tab.readOnly,
            automaticLayout: true,
            fontFamily: "Consolas, Menlo, monospace",
            fontSize: 13,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            tabSize: 4,
            insertSpaces: true,
            wordWrap: "off",
          }}
          onMount={handleEditorMount}
          onChange={handleEditorChange}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center text-xs text-stone-400"
          data-testid="code-editor-loading"
        >
          Loading editor…
        </div>
      )}
    </div>
  );
}

// Minimal subset of `@monaco-editor/react`'s EditorProps that we use.
// Declared inline so we don't pull the type at module scope (which would
// defeat the lazy-import goal — TS can drop type-only imports, but
// keeping this explicit makes the intent obvious to future readers).
interface EditorComponentProps {
  height?: string | number;
  width?: string | number;
  theme?: string;
  language?: string;
  value?: string;
  path?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  options?: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onMount?: (editor: any, monaco: any) => void;
  onChange?: (value: string | undefined) => void;
}

export default CodeEditor;
