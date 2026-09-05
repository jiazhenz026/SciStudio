/**
 * ADR-054 spec 4 (T-004) — the two states of a cell body (FR-008, FR-009).
 *
 * `NotebookShell.test.tsx` proves *how many* cells carry an editor. This file
 * proves what each of the two states is: the editor is the bundle's Monaco with
 * the cell's source and language, and the static half is the same source,
 * highlighted, with no editor behind it at all.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CellEditor, StaticCellSource, editorHeightFor, highlightPython } from "./CellEditor";

vi.mock("@monaco-editor/react", () => ({
  default: (props: {
    path?: string;
    value?: string;
    language?: string;
    height?: number | string;
    options?: { readOnly?: boolean };
    onChange?: (value: string | undefined) => void;
  }) => (
    <textarea
      data-height={String(props.height)}
      data-language={props.language}
      data-testid={`monaco-${props.path}`}
      onChange={(event) => props.onChange?.(event.target.value)}
      readOnly={props.options?.readOnly}
      value={props.value ?? ""}
    />
  ),
}));

afterEach(cleanup);

describe("CellEditor", () => {
  it("mounts the editor with the cell's source, language and model path", async () => {
    render(<CellEditor cellId="c1" language="python" onChange={vi.fn()} value="df = load()" />);
    const editor = await screen.findByTestId("monaco-explore-cell/c1");
    expect((editor as HTMLTextAreaElement).value).toBe("df = load()");
    expect(editor.getAttribute("data-language")).toBe("python");
  });

  it("hands every keystroke back and holds none of it", async () => {
    const onChange = vi.fn();
    render(<CellEditor cellId="c1" language="python" onChange={onChange} value="a" />);
    const editor = await screen.findByTestId("monaco-explore-cell/c1");
    fireEvent.change(editor, { target: { value: "ab" } });
    expect(onChange).toHaveBeenCalledWith("ab");
    // The editor is controlled by `value`: it did not keep the new text.
    expect((screen.getByTestId("monaco-explore-cell/c1") as HTMLTextAreaElement).value).toBe("a");
  });

  it("renders a disabled cell read-only", async () => {
    render(<CellEditor cellId="c2" language="python" onChange={vi.fn()} readOnly value="x" />);
    const editor = await screen.findByTestId("monaco-explore-cell/c2");
    expect((editor as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("shows the source while the editor module is still loading", async () => {
    // The very first mount in this file races the lazy import; the static text
    // is what the person reads meanwhile, so it must be the real source.
    const { unmount } = render(
      <CellEditor cellId="c3" language="python" onChange={vi.fn()} value="import os" />,
    );
    await waitFor(() => expect(screen.queryByTestId("monaco-explore-cell/c3")).not.toBeNull());
    unmount();
  });
});

describe("editorHeightFor", () => {
  it("sizes the editor to the cell and caps a very long one", () => {
    expect(editorHeightFor("one line")).toBeLessThan(editorHeightFor("one\ntwo\nthree"));
    expect(editorHeightFor("")).toBe(editorHeightFor("one line"));
    expect(editorHeightFor("x\n".repeat(500))).toBe(480);
  });
});

describe("StaticCellSource", () => {
  it("renders the source with no editor behind it", () => {
    render(<StaticCellSource cellId="c9" language="python" source={"def f():\n    return 1"} />);
    expect(screen.getByTestId("explore-cell-static-c9").textContent).toBe("def f():\n    return 1");
    expect(screen.queryByTestId("monaco-explore-cell/c9")).toBeNull();
  });

  it("renders markdown source as plain text, not as Python", () => {
    render(<StaticCellSource cellId="m1" language="markdown" source="# not a comment" />);
    const spans = screen.getByTestId("explore-cell-static-m1").querySelectorAll("span");
    expect(spans).toHaveLength(1);
  });
});

describe("highlightPython", () => {
  it("separates comments, strings, numbers and keywords from the rest", () => {
    const tokens = highlightPython('x = 1  # note\nif "s":\n    pass');
    const byKind = (kind: string) =>
      tokens.filter((token) => token.kind === kind).map((token) => token.text);
    expect(byKind("comment")).toEqual(["# note"]);
    expect(byKind("string")).toEqual(['"s"']);
    expect(byKind("number")).toEqual(["1"]);
    expect(byKind("keyword")).toEqual(["if", "pass"]);
    // Nothing is lost: the runs reassemble into the source exactly.
    expect(tokens.map((token) => token.text).join("")).toBe('x = 1  # note\nif "s":\n    pass');
  });

  it("does not swallow the rest of the cell on an unterminated string", () => {
    const source = "x = 'unterminated\ny = 2";
    expect(
      highlightPython(source)
        .map((token) => token.text)
        .join(""),
    ).toBe(source);
  });

  it("keeps a triple-quoted string whole", () => {
    const source = 'doc = """line one\nline two"""\n';
    const tokens = highlightPython(source);
    expect(tokens.filter((token) => token.kind === "string")).toHaveLength(1);
    expect(tokens.map((token) => token.text).join("")).toBe(source);
  });

  it("returns one plain run for an empty cell", () => {
    expect(highlightPython("")).toEqual([]);
  });
});
