/**
 * ADR-036 §3.1 / §3.3 / §3.7 — CodeEditor (I36b) tests.
 *
 * Mocks `@monaco-editor/react` so jsdom doesn't need to load real Monaco.
 * Mirrors the xterm-mock pattern in
 * ``frontend/src/components/AIChat/__tests__/TerminalView.test.tsx``.
 */

import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CodeEditor } from "../CodeEditor";
import type { FileTab } from "../../store/types";

// --- Monaco React mock state ---------------------------------------------
interface DefinedTheme {
  base: string;
  inherit: boolean;
  rules: Array<Record<string, unknown>>;
  colors: Record<string, string>;
}

interface MockCompletionProvider {
  triggerCharacters?: string[];
  provideCompletionItems: (
    model: {
      uri?: { path?: string };
      getLineContent?: (lineNumber: number) => string;
      getWordUntilPosition?: (position: { lineNumber: number; column: number }) => {
        startColumn: number;
        endColumn: number;
      };
    },
    position: { lineNumber: number; column: number },
  ) => { suggestions: Array<{ label: string; insertText: string }> };
}

interface RegisteredCompletionProvider {
  language: string;
  provider: MockCompletionProvider;
}

interface MockEditorState {
  lastProps: Record<string, unknown> | null;
  // The latest mounted-editor object passed to onMount.
  lastEditor: FakeMonacoEditor | null;
  lastMonaco: FakeMonacoNamespace | null;
  // Triggered onChange handler (so tests can simulate edits).
  onChangeCb: ((value: string | undefined) => void) | null;
  // Last setModelMarkers call.
  markersByOwner: Map<string, unknown[]>;
  // Themes registered via monaco.editor.defineTheme during beforeMount.
  definedThemes: Map<string, DefinedTheme>;
  completionProviders: RegisteredCompletionProvider[];
}

const editorState: MockEditorState = {
  lastProps: null,
  lastEditor: null,
  lastMonaco: null,
  onChangeCb: null,
  markersByOwner: new Map(),
  definedThemes: new Map(),
  completionProviders: [],
};

class FakeMonacoEditor {
  options: Record<string, unknown> = {};
  model: { id: string; lang: string };
  commands: Array<{ keybinding: number; handler: () => void }> = [];
  constructor(initialOpts: Record<string, unknown>, language: string) {
    this.options = { ...initialOpts };
    this.model = { id: "m1", lang: language };
  }
  updateOptions(opts: Record<string, unknown>) {
    Object.assign(this.options, opts);
  }
  getModel() {
    return this.model;
  }
  addCommand(keybinding: number, handler: () => void) {
    this.commands.push({ keybinding, handler });
  }
}

class FakeMonacoNamespace {
  KeyMod = { CtrlCmd: 0x800 };
  KeyCode = { KeyS: 49 };
  languages = {
    CompletionItemKind: { Function: 1, Property: 10 },
    CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
    registerCompletionItemProvider: (language: string, provider: MockCompletionProvider) => {
      editorState.completionProviders.push({ language, provider });
      return { dispose: vi.fn() };
    },
  };
  editor = {
    setModelMarkers: (_model: unknown, owner: string, markers: unknown[]) => {
      editorState.markersByOwner.set(owner, markers);
    },
    setModelLanguage: (model: { lang: string }, lang: string) => {
      model.lang = lang;
    },
    defineTheme: (name: string, data: DefinedTheme) => {
      editorState.definedThemes.set(name, data);
    },
  };
}

vi.mock("@monaco-editor/react", () => {
  function MockEditor(props: Record<string, unknown>) {
    editorState.lastProps = props;
    // Mount synchronously on first render.
    const language = (props.language as string) ?? "plaintext";
    const options = (props.options as Record<string, unknown>) ?? {};
    if (!editorState.lastEditor) {
      editorState.lastEditor = new FakeMonacoEditor(options, language);
      editorState.lastMonaco = new FakeMonacoNamespace();
      // beforeMount runs before onMount in real @monaco-editor/react; it
      // receives the monaco namespace so the component can register themes.
      const beforeMount = props.beforeMount as ((m: FakeMonacoNamespace) => void) | undefined;
      beforeMount?.(editorState.lastMonaco);
      const onMount = props.onMount as
        | ((e: FakeMonacoEditor, m: FakeMonacoNamespace) => void)
        | undefined;
      // Schedule onMount so React effect ordering matches real Monaco.
      Promise.resolve().then(() => {
        onMount?.(editorState.lastEditor!, editorState.lastMonaco!);
      });
    } else {
      // Re-render: propagate options updates as Monaco would via prop diff.
      editorState.lastEditor.updateOptions(options);
    }
    editorState.onChangeCb = props.onChange as ((value: string | undefined) => void) | null;
    return null;
  }
  return { default: MockEditor };
});

// --- Test fixtures + lifecycle --------------------------------------------

function makeFileTab(overrides: Partial<FileTab> = {}): FileTab {
  return {
    kind: "file",
    id: "file:blocks/sample.py",
    filePath: "blocks/sample.py",
    displayName: "sample.py",
    language: "python",
    content: "import os\n",
    contentLoadedAt: 0,
    dirty: false,
    readOnly: false,
    ...overrides,
  };
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  editorState.lastProps = null;
  editorState.lastEditor = null;
  editorState.lastMonaco = null;
  editorState.onChangeCb = null;
  editorState.markersByOwner.clear();
  editorState.definedThemes.clear();
  editorState.completionProviders = [];
  fetchSpy = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ diagnostics: [] }),
  });
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("CodeEditor", () => {
  it("renders the Monaco editor for a Python file tab", async () => {
    render(<CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={vi.fn()} />);
    await waitFor(() => expect(editorState.lastProps).not.toBeNull());
    expect(editorState.lastProps).toMatchObject({
      language: "python",
      value: "import os\n",
      path: "blocks/sample.py",
    });
    expect((editorState.lastProps?.options as Record<string, unknown>).readOnly).toBe(false);
  });

  it("propagates content changes via onContentChange", async () => {
    const onContentChange = vi.fn();
    render(<CodeEditor tab={makeFileTab()} onContentChange={onContentChange} onSave={vi.fn()} />);
    await waitFor(() => expect(editorState.onChangeCb).not.toBeNull());
    act(() => {
      editorState.onChangeCb?.("new content");
    });
    expect(onContentChange).toHaveBeenCalledWith("new content");
  });

  it("debounces lint requests (5 rapid edits → 1 POST after 600 ms)", async () => {
    vi.useFakeTimers();
    render(<CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={vi.fn()} />);
    // Wait for the dynamic import + onMount to resolve.
    await vi.waitFor(() => expect(editorState.onChangeCb).not.toBeNull());
    // The onMount handler also schedules an initial lint; clear that timer
    // by counting fetches at 0 first.
    expect(fetchSpy).toHaveBeenCalledTimes(0);
    // Fire 5 rapid edits.
    for (let i = 0; i < 5; i++) {
      act(() => {
        editorState.onChangeCb?.(`x${i}`);
      });
    }
    // 599 ms — no fetch yet.
    await act(async () => {
      vi.advanceTimersByTime(599);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(0);
    // 1 ms more → exactly one fetch.
    await act(async () => {
      vi.advanceTimersByTime(2);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/lint/python",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders Monaco markers from /api/lint/python response", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        diagnostics: [
          {
            line: 1,
            column: 1,
            end_line: 1,
            end_column: 10,
            code: "F401",
            severity: "warning",
            message: "imported but unused",
          },
        ],
      }),
    });
    vi.useFakeTimers();
    render(<CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={vi.fn()} />);
    await vi.waitFor(() => expect(editorState.onChangeCb).not.toBeNull());
    act(() => {
      editorState.onChangeCb?.("import os\n");
    });
    await act(async () => {
      vi.advanceTimersByTime(601);
    });
    // Let the resolved fetch promise settle.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const markers = editorState.markersByOwner.get("ruff");
    expect(markers).toBeDefined();
    expect(markers).toHaveLength(1);
    expect((markers as Array<{ code: string }>)[0].code).toBe("F401");
  });

  it("respects tab.readOnly via editor options", async () => {
    const { rerender } = render(
      <CodeEditor
        tab={makeFileTab({ readOnly: true })}
        onContentChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    await waitFor(() => expect(editorState.lastEditor).not.toBeNull());
    expect(editorState.lastEditor?.options.readOnly).toBe(true);
    // Flip readOnly false → updateOptions should propagate.
    rerender(
      <CodeEditor
        tab={makeFileTab({ readOnly: false })}
        onContentChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    await waitFor(() => expect(editorState.lastEditor?.options.readOnly).toBe(false));
  });

  it("Ctrl+S inside the editor invokes onSave (via addCommand)", async () => {
    const onSave = vi.fn();
    render(<CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={onSave} />);
    await waitFor(() => expect(editorState.lastEditor).not.toBeNull());
    // The editor should have registered a single Ctrl+S command.
    const cmd = editorState.lastEditor?.commands[0];
    expect(cmd).toBeDefined();
    cmd?.handler();
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("Ctrl+S on the host container also invokes onSave (loading fallback)", async () => {
    const onSave = vi.fn();
    const { container } = render(
      <CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={onSave} />,
    );
    const host = container.querySelector("[data-testid='code-editor']") as HTMLElement;
    expect(host).toBeTruthy();
    // Synthesize a Ctrl+S keydown bubbling up from within the host.
    const event = new KeyboardEvent("keydown", {
      key: "s",
      ctrlKey: true,
      bubbles: true,
    });
    host.dispatchEvent(event);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("registers the scistudio-soft-dark Monaco theme via beforeMount", async () => {
    render(<CodeEditor tab={makeFileTab()} onContentChange={vi.fn()} onSave={vi.fn()} />);
    await waitFor(() => expect(editorState.lastProps).not.toBeNull());
    expect(editorState.lastProps?.theme).toBe("scistudio-soft-dark");
    // beforeMount fires synchronously on first render — theme is registered
    // before onMount resolves on the next microtask.
    const theme = editorState.definedThemes.get("scistudio-soft-dark");
    expect(theme).toBeDefined();
    expect(theme?.base).toBe("vs-dark");
    expect(theme?.inherit).toBe(true);
    // Background MUST be the soft warm gray (#282c34), not pure vs-dark #1e1e1e.
    expect(theme?.colors["editor.background"]).toBe("#282c34");
  });

  it("registers SciStudio plot context completions for Python and R render files", async () => {
    render(
      <CodeEditor
        tab={makeFileTab({ filePath: "plots/qc/render.py", content: "context." })}
        onContentChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    await waitFor(() => expect(editorState.lastProps).not.toBeNull());
    expect(editorState.completionProviders.map((entry) => entry.language)).toEqual(["python", "r"]);

    const pythonProvider = editorState.completionProviders.find(
      (entry) => entry.language === "python",
    )?.provider;
    expect(pythonProvider).toBeDefined();
    const pythonResult = pythonProvider?.provideCompletionItems(
      {
        uri: { path: "/plots/qc/render.py" },
        getLineContent: () => "context.",
        getWordUntilPosition: () => ({ startColumn: 9, endColumn: 9 }),
      },
      { lineNumber: 1, column: 9 },
    );
    expect(pythonResult?.suggestions.map((item) => item.label)).toEqual(
      expect.arrayContaining(["to_dataframe", "items", "plt", "save_figure", "save_plot"]),
    );

    const rProvider = editorState.completionProviders.find(
      (entry) => entry.language === "r",
    )?.provider;
    const rResult = rProvider?.provideCompletionItems(
      {
        uri: { path: "/plots/qc/render.R" },
        getLineContent: () => "context$",
        getWordUntilPosition: () => ({ startColumn: 9, endColumn: 9 }),
      },
      { lineNumber: 1, column: 9 },
    );
    expect(rResult?.suggestions.map((item) => item.label)).toEqual(
      expect.arrayContaining(["to_dataframe", "save_plot", "save_figure"]),
    );

    const nonPlotResult = pythonProvider?.provideCompletionItems(
      {
        uri: { path: "/blocks/sample.py" },
        getLineContent: () => "context.",
        getWordUntilPosition: () => ({ startColumn: 9, endColumn: 9 }),
      },
      { lineNumber: 1, column: 9 },
    );
    expect(nonPlotResult?.suggestions).toEqual([]);
  });
});
